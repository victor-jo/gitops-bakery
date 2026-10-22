// Creates, inspects and deletes GitOps apps: two GitLab repos, CI variables, a Harbor repo and an Argo CD Application
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { GITLAB_HOST_URL, GITLAB_INTERNAL_URL } from "../lib/config.js";
import type { ArgoCD } from "../lib/argocd.js";
import { asset } from "../lib/assets.js";
import type { GitLab, Pipeline } from "../lib/gitlab.js";
import type { Harbor } from "../lib/harbor.js";
import { registryHost } from "../lib/names.js";
import { assetPath } from "../lib/paths.js";
import type { Secrets } from "../lib/secrets.js";
import { loadState, saveState } from "../lib/state.js";
import { render } from "../lib/template.js";
import { waitFor } from "../lib/wait.js";
import { getFastSyncMode } from "../steps/fast-sync.js";
import { HARBOR_APPS_PROJECT, HARBOR_ROBOT } from "../steps/harbor.js";
import { validateAppName } from "./names.js";
import { allocatePort } from "./ports.js";

export type AppDeps = {
  gitlab: GitLab;
  harbor: Harbor;
  argocd: ArgoCD;
  secrets: Secrets;
  kube: (args: string[]) => Promise<string>;
  pollMs?: number;
};
export type Template = "fastapi";
export type TemplateVars = { name: string; registry: string; nodePort: number; image: string };

const APPS_GROUP = "apps";
const SERVICE_ROOT = "service-root";
const SERVICE_REPO = "devops/service";

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((n) => (statSync(join(dir, n)).isDirectory() ? walk(join(dir, n)) : [join(dir, n)]));
}

export function templateFiles(kind: "app" | "manifests", vars: TemplateVars, template: Template = "fastapi") {
  const root = assetPath("templates", template, kind);
  return walk(root).sort().map((full) => ({ path: relative(root, full), content: render(readFileSync(full, "utf8"), vars) }));
}

export function appUrl(nodePort: number): string {
  return `http://localhost:${nodePort}`;
}

export async function createApp(deps: AppDeps, name: string, template: Template) {
  validateAppName(name);
  const state = loadState();
  if (state.apps[name]) throw new Error(`App "${name}" already exists`);
  const mode = getFastSyncMode();
  const nodePort = allocatePort(state.apps);
  // Reserve the name and port before the first await so parallel tool calls cannot pick the same ones
  saveState({ ...state, apps: { ...state.apps, [name]: { name, nodePort, createdAt: new Date().toISOString() } } });
  const vars = { name, registry: registryHost(), nodePort, image: `${registryHost()}/${HARBOR_APPS_PROJECT}/${name}` };
  const repo = `${APPS_GROUP}/${name}`;
  const manifestsRepo = `${repo}-manifests`;
  const { gitlab, secrets } = deps;
  const created: string[] = [];
  let applicationCommitted = false;

  try {
    await gitlab.createProject(APPS_GROUP, `${name}-manifests`);
    created.push(manifestsRepo);
    await gitlab.commitFiles(manifestsRepo, templateFiles("manifests", vars, template), `Create ${name} manifests`);
    const manifestToken = await gitlab.createProjectToken(manifestsRepo, "ci", ["write_repository"]);
    await gitlab.createProject(APPS_GROUP, name);
    created.push(repo);
    // raw: GitLab would otherwise expand the "$apps" inside the robot name
    await gitlab.setVariable(repo, "HARBOR_USER", `robot$${HARBOR_APPS_PROJECT}+${HARBOR_ROBOT}`, { raw: true, masked: false });
    await gitlab.setVariable(repo, "HARBOR_PASSWORD", secrets.harborRobotSecret!, { raw: true, masked: true });
    await gitlab.setVariable(repo, "MANIFEST_TOKEN", manifestToken, { raw: true, masked: true });
    if (mode === "ci-refresh") await gitlab.setVariable(repo, "ARGOCD_TOKEN", secrets.argocdCiToken!, { raw: true, masked: true });
    await gitlab.commitFiles(repo, templateFiles("app", vars, template), `Create ${name} from the ${template} template`);
    await gitlab.commitFiles(
      SERVICE_REPO,
      [{ path: `apps/${name}.yaml`, content: asset("gitops/app-application.yaml.tmpl", { name, gitlabUrl: GITLAB_INTERNAL_URL }) }],
      `Deploy ${name}`,
    );
    applicationCommitted = true;
    // service-root would otherwise notice the new Application only on its next 3-minute poll;
    // a failed refresh only means waiting for that poll, so it must not undo the app
    await deps.argocd.refresh(SERVICE_ROOT).catch(() => undefined);
  } catch (e) {
    // Undo only what this call created; a pre-existing project with the same path is left alone
    if (applicationCommitted) await gitlab.deleteFile(SERVICE_REPO, `apps/${name}.yaml`, `Remove ${name}`).catch(() => undefined);
    for (const p of created.reverse()) await gitlab.deleteProject(p).catch(() => undefined);
    releaseApp(name);
    throw e;
  }
  return {
    url: appUrl(nodePort),
    pipelineUrl: `${GITLAB_HOST_URL}/${repo}/-/pipelines`,
    repo: `${GITLAB_HOST_URL}/${repo}`,
    manifestsRepo: `${GITLAB_HOST_URL}/${manifestsRepo}`,
  };
}

function releaseApp(name: string): void {
  const s = loadState();
  delete s.apps[name];
  saveState(s);
}

export type AppStatusReport = {
  name: string;
  url: string | null;
  pipeline: Pipeline | null;
  tags: string[];
  sync: string;
  health: string;
};

export async function appStatus(deps: AppDeps, name: string): Promise<AppStatusReport> {
  validateAppName(name);
  const rec = loadState().apps[name];
  if (!rec) throw new Error(`App "${name}" does not exist`);
  const [pipeline, tags, argo] = await Promise.all([
    deps.gitlab.latestPipeline(`${APPS_GROUP}/${name}`),
    deps.harbor.listTags(HARBOR_APPS_PROJECT, name),
    deps.argocd.getApp(name),
  ]);
  return { name, url: appUrl(rec.nodePort), pipeline, tags, sync: argo?.sync ?? "Missing", health: argo?.health ?? "Missing" };
}

export async function deleteApp(deps: AppDeps, name: string): Promise<void> {
  validateAppName(name);
  // Removing the Application from git lets Argo CD cascade-delete the workload through its finalizer
  await deps.gitlab.deleteFile(SERVICE_REPO, `apps/${name}.yaml`, `Remove ${name}`);
  await deps.argocd.refresh(SERVICE_ROOT).catch(() => undefined);
  await waitFor(`Argo CD to remove ${name}`, async () => {
    const app = await deps.argocd.getApp(name);
    return { ok: app === null, state: app ? `${app.sync}/${app.health}` : "gone" };
  }, 3 * 60_000, deps.pollMs ?? 3000).catch(() => undefined);
  // Deleting the namespace is the backstop that frees the NodePort even if the cascade did not finish
  await deps.kube(["delete", "namespace", `app-${name}`, "--ignore-not-found", "--wait=true", "--timeout=180s"]).catch(() => undefined);
  await deps.gitlab.deleteProject(`${APPS_GROUP}/${name}`);
  await deps.gitlab.deleteProject(`${APPS_GROUP}/${name}-manifests`);
  await deps.harbor.deleteRepository(HARBOR_APPS_PROJECT, name);
  // The port goes back to the pool last, once nothing in the cluster can still hold it
  releaseApp(name);
}
