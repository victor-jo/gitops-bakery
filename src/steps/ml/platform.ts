// Commits the ML Applications (MLflow, Jupyter, Feast, KFP) to devops/platform and waits until Argo CD has them running
import { GITLAB_HOST_URL, GITLAB_INTERNAL_URL } from "../../lib/config.js";
import type { AppStatus } from "../../lib/argocd.js";
import { GitLab } from "../../lib/gitlab.js";
import type { MlHosts } from "../../lib/state.js";
import { waitFor } from "../../lib/wait.js";
import { argocdAdmin, gitopsFiles, type RepoFile } from "../bootstrap.js";
import type { Step } from "../types.js";
import { deleteGatewayProbes, mlHosts } from "./gateways.js";

export const ML_APPS = ["feast-operator", "mlflow", "jupyter", "feast-store", "kfp", "monitoring"];

// Earlier hand-built labs published these NodePorts inside the 30010-30019 app range; the Ingress names replace them
export const STALE_PLATFORM_FILES = [
  "feast/manifests/online-nodeport.yaml",
  "kfp/manifests/20-ui-nodeport.yaml",
  "jupyter/manifests/notebook-configmap.yaml",
];

export function mlPlatformFiles(hosts: MlHosts): RepoFile[] {
  const vars = {
    gitlabUrl: GITLAB_INTERNAL_URL,
    mlflowHost: hosts.mlflow,
    jupyterHost: hosts.jupyter,
    feastHost: hosts.feast,
    kfpHost: hosts.kfp,
    grafanaHost: hosts.grafana,
  };
  // monitoring.yaml from the base set gains the optional Grafana ingress values file, so both sets go in together
  return [...gitopsFiles("platform", vars), ...gitopsFiles("platform-ml", vars)];
}

export async function changedFiles(gitlab: Pick<GitLab, "readFile">, project: string, files: RepoFile[]): Promise<RepoFile[]> {
  const out: RepoFile[] = [];
  for (const f of files) if ((await gitlab.readFile(project, f.path)) !== f.content) out.push(f);
  return out;
}

// Right after a commit an app still reports Synced for the previous revision, so health alone would end the wait too early
export function syncedAt(s: AppStatus | null, head: string): boolean {
  if (!s || s.sync !== "Synced" || s.health !== "Healthy") return false;
  return s.revision === head || (s.revisions ?? []).includes(head);
}

export const mlPlatformStep: Step = {
  id: "ml-platform",
  title: "ML apps in devops/platform (Argo CD)",
  async run(ctx) {
    const project = "devops/platform";
    const gitlab = new GitLab(GITLAB_HOST_URL, ctx.secrets.gitlabPat!);
    const changed = await changedFiles(gitlab, project, mlPlatformFiles(mlHosts()));
    if (changed.length) await gitlab.commitFiles(project, changed, "Add the ML lab (MLflow, Jupyter, Feast, KFP) by gitops-bakery --with-ml");
    for (const path of STALE_PLATFORM_FILES)
      if ((await gitlab.readFile(project, path)) !== null) await gitlab.deleteFile(project, path, `Remove ${path}, which --with-ml no longer uses`);
    const head = await gitlab.branchHead(project);

    const argocd = await argocdAdmin(ctx.secrets.argocdAdmin!);
    await argocd.refresh("platform-root");
    for (const name of ML_APPS) {
      // Asking for a refresh on every poll skips Argo CD's 3-minute git poll
      await waitFor(`Argo CD application ${name} at ${head.slice(0, 8)}`, async () => {
        const s = await argocd.getApp(name);
        if (s && !syncedAt(s, head)) await argocd.refresh(name);
        return { ok: syncedAt(s, head), state: s ? `${s.sync}/${s.health} at ${(s.revision || s.revisions?.join(",") || "?").slice(0, 8)}` : "missing" };
      }, 30 * 60_000, 10_000);
    }
    await deleteGatewayProbes();
  },
};
