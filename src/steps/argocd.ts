// Installs Argo CD and records its generated admin password
import { VERSIONS } from "../lib/config.js";
import { asset } from "../lib/assets.js";
import { helmUpgrade } from "../lib/helm.js";
import { secretValue } from "../lib/kube.js";
import { updateSecrets } from "../lib/secrets.js";
import type { Step } from "./types.js";

export const argocdStep: Step = {
  id: "argocd",
  title: "Argo CD",
  async run(ctx) {
    await helmUpgrade({
      release: "argocd",
      chart: "argo/argo-cd",
      version: VERSIONS.argocdChart,
      ns: "argocd",
      repo: { name: "argo", url: "https://argoproj.github.io/argo-helm" },
      values: asset("values/argocd.yaml"),
    });
    ctx.secrets = updateSecrets({ argocdAdmin: await secretValue("argocd", "argocd-initial-admin-secret", "password") });
  },
};
