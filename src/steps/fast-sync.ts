// Sets up how app changes reach Argo CD without the 3-minute poll: a refresh call from CI with a narrow token
import { ARGOCD_HOST_URL, VERSIONS } from "../lib/config.js";
import { asset } from "../lib/assets.js";
import { helmUpgrade } from "../lib/helm.js";
import { loadState, saveState } from "../lib/state.js";
import { updateSecrets } from "../lib/secrets.js";
import type { Step } from "./types.js";

export type FastSyncMode = "webhook" | "ci-refresh";

export function getFastSyncMode(): FastSyncMode {
  const mode = loadState().fastSync;
  if (!mode) throw new Error("Fast-sync mode is not set yet; run the fast-sync install step first");
  return mode;
}

async function adminToken(password: string): Promise<string> {
  const res = await fetch(`${ARGOCD_HOST_URL}/api/v1/session`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: "admin", password }),
  });
  if (!res.ok) throw new Error(`Argo CD login failed: ${res.status}`);
  return ((await res.json()) as { token: string }).token;
}

export const fastSyncStep: Step = {
  id: "fast-sync",
  title: "Fast sync (CI refresh token)",
  async run(ctx) {
    // Re-apply Argo CD values so clusters installed before the ci account existed get it too
    await helmUpgrade({
      release: "argocd",
      chart: "argo/argo-cd",
      version: VERSIONS.argocdChart,
      ns: "argocd",
      repo: { name: "argo", url: "https://argoproj.github.io/argo-helm" },
      values: asset("values/argocd.yaml"),
    });
    const admin = await adminToken(ctx.secrets.argocdAdmin!);
    const res = await fetch(`${ARGOCD_HOST_URL}/api/v1/account/ci/token`, {
      method: "POST",
      headers: { authorization: `Bearer ${admin}`, "content-type": "application/json" },
      body: JSON.stringify({ name: "gitops-bakery-ci" }),
    });
    if (!res.ok) throw new Error(`Could not create the Argo CD ci token: ${res.status} ${await res.text()}`);
    ctx.secrets = updateSecrets({ argocdCiToken: ((await res.json()) as { token: string }).token });
    saveState({ ...loadState(), fastSync: "ci-refresh" });
  },
};
