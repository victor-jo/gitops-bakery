// Builds live API clients for MCP tools from the stored lab secrets
import type { AppDeps } from "../apps/lifecycle.js";
import { ArgoCD } from "../lib/argocd.js";
import { ARGOCD_HOST_URL, GITLAB_HOST_URL, HARBOR_HOST_URL } from "../lib/config.js";
import { GitLab } from "../lib/gitlab.js";
import { Harbor } from "../lib/harbor.js";
import { kubectl } from "../lib/kube.js";
import { loadOrCreateSecrets } from "../lib/secrets.js";

export async function liveDeps(): Promise<AppDeps> {
  const secrets = loadOrCreateSecrets();
  if (!secrets.gitlabPat || !secrets.argocdAdmin) throw new Error("The lab is not installed yet; run `gitops-bakery install` first");
  return {
    secrets,
    gitlab: new GitLab(GITLAB_HOST_URL, secrets.gitlabPat),
    harbor: new Harbor(HARBOR_HOST_URL, "admin", secrets.harborAdmin),
    argocd: await ArgoCD.login(ARGOCD_HOST_URL, "admin", secrets.argocdAdmin),
    kube: (args) => kubectl(args),
  };
}
