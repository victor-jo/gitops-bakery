// Seeds devops/platform and devops/service in GitLab and applies the two root Applications
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { ARGOCD_HOST_URL, GITLAB_HOST_URL, GITLAB_INTERNAL_URL } from "../lib/config.js";
import { ArgoCD } from "../lib/argocd.js";
import { GitLab } from "../lib/gitlab.js";
import { applyYaml, kubectl } from "../lib/kube.js";
import { assetPath } from "../lib/paths.js";
import { render } from "../lib/template.js";
import { waitFor } from "../lib/wait.js";
import type { Step } from "./types.js";

export type RepoFile = { path: string; content: string };

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    return statSync(full).isDirectory() ? walk(full) : [full];
  });
}

// Grafana dashboards use {{label}} legends of their own, so JSON files are committed verbatim
export function gitopsFiles(repo: "platform" | "service", vars: Record<string, string>): RepoFile[] {
  const root = assetPath("assets", "gitops", repo);
  return walk(root)
    .sort()
    .map((full) => {
      const raw = readFileSync(full, "utf8");
      return { path: relative(root, full), content: full.endsWith(".json") ? raw : render(raw, vars) };
    });
}

export const ROOT_APPS = ["platform-root", "service-root"];

export async function argocdAdmin(password: string): Promise<ArgoCD> {
  return ArgoCD.login(ARGOCD_HOST_URL, "admin", password);
}

export async function waitHealthy(argocd: ArgoCD, names: string[], timeoutMs: number): Promise<void> {
  for (const name of names) {
    await waitFor(`Argo CD application ${name}`, async () => {
      const s = await argocd.getApp(name);
      return { ok: s?.sync === "Synced" && s.health === "Healthy", state: s ? `${s.sync}/${s.health}` : "missing" };
    }, timeoutMs);
  }
}

// Labs bootstrapped before service-root allowed an empty sync get the updated root.yaml through this step
export const serviceRootAllowEmptyStep: Step = {
  id: "service-root-allow-empty",
  title: "service-root may prune its last app",
  async run(ctx) {
    const gitlab = new GitLab(GITLAB_HOST_URL, ctx.secrets.gitlabPat!);
    const root = gitopsFiles("service", { gitlabUrl: GITLAB_INTERNAL_URL }).find((f) => f.path === "root.yaml")!;
    await gitlab.commitFiles("devops/service", [root], "Let service-root prune its last app").catch((e: Error) => {
      // A lab bootstrapped by this version already has the same content, which GitLab rejects as an empty commit
      if (!/no changes|A file with this name already exists|empty/i.test(e.message)) throw e;
    });
    await applyYaml(root.content);
  },
};

export const bootstrapStep: Step = {
  id: "bootstrap",
  title: "GitOps repos and monitoring",
  async run(ctx) {
    const gitlab = new GitLab(GITLAB_HOST_URL, ctx.secrets.gitlabPat!);
    const vars = { gitlabUrl: GITLAB_INTERNAL_URL };
    await kubectl(["create", "namespace", "monitoring"]).catch(() => undefined);
    await applyYaml(JSON.stringify({
      apiVersion: "v1",
      kind: "Secret",
      metadata: { name: "grafana-admin", namespace: "monitoring" },
      stringData: { "admin-user": "admin", "admin-password": ctx.secrets.grafanaAdmin },
    }));
    for (const repo of ["platform", "service"] as const) {
      const project = await gitlab.ensureProject("devops", repo);
      await gitlab.commitFiles(project.pathWithNamespace, gitopsFiles(repo, vars), "Seed by gitops-bakery");
      await applyYaml(gitopsFiles(repo, vars).find((f) => f.path === "root.yaml")!.content);
    }
    await waitHealthy(await argocdAdmin(ctx.secrets.argocdAdmin!), [...ROOT_APPS, "monitoring"], 15 * 60_000);
  },
};
