// Installs the CloudNativePG operator and a single-instance PostgreSQL 17 cluster for GitLab
import { VERSIONS } from "../lib/config.js";
import { asset } from "../lib/assets.js";
import { run } from "../lib/exec.js";
import { applyYaml, kubeContext, kubectl } from "../lib/kube.js";
import { waitFor } from "../lib/wait.js";
import type { Step } from "./types.js";

const minor = VERSIONS.cnpg.split(".").slice(0, 2).join(".");
const OPERATOR_URL = `https://raw.githubusercontent.com/cloudnative-pg/cloudnative-pg/release-${minor}/releases/cnpg-${VERSIONS.cnpg}.yaml`;

export const cnpgStep: Step = {
  id: "cnpg",
  title: "PostgreSQL (CloudNativePG)",
  async run() {
    const res = await fetch(OPERATOR_URL);
    if (!res.ok) throw new Error(`Could not download ${OPERATOR_URL}: HTTP ${res.status}`);
    await applyYaml(await res.text(), { serverSide: true });
    await kubectl(["-n", "cnpg-system", "rollout", "status", "deploy/cnpg-controller-manager", "--timeout=5m"]);
    await kubectl(["create", "namespace", "gitlab"]).catch(() => undefined);
    // The operator's webhook can reject requests for a few seconds after the rollout reports ready
    await waitFor("CloudNativePG webhook", async () => {
      const r = await run("kubectl", ["--context", kubeContext(), "apply", "-f", "-"],
        { input: asset("deps/cnpg-cluster.yaml"), allowFail: true });
      return { ok: r.code === 0, state: r.stderr.trim().split("\n").at(-1) ?? "" };
    }, 3 * 60_000);
    await waitFor("PostgreSQL cluster gitlab-rails-db", async () => {
      const phase = await kubectl(["-n", "gitlab", "get", "cluster", "gitlab-rails-db", "-o", "jsonpath={.status.phase}"]);
      return { ok: phase === "Cluster in healthy state", state: phase };
    }, 10 * 60_000);
  },
};
