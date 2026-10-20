// Registers an instance runner and installs GitLab Runner with the Kubernetes executor
import { GITLAB_HOST_URL, VERSIONS } from "../lib/config.js";
import { asset } from "../lib/assets.js";
import { GitLab } from "../lib/gitlab.js";
import { helmUpgrade } from "../lib/helm.js";
import { applyYaml, kubectl } from "../lib/kube.js";
import { waitFor } from "../lib/wait.js";
import type { Step } from "./types.js";

const RUNNER_NAME = "gitops-bakery";

async function tokenSecretExists(): Promise<boolean> {
  return kubectl(["-n", "gitlab-runner", "get", "secret", "gitlab-runner-token"]).then(() => true, () => false);
}

export const gitlabRunnerStep: Step = {
  id: "runner",
  title: "GitLab Runner",
  async run(ctx) {
    const gitlab = new GitLab(GITLAB_HOST_URL, ctx.secrets.gitlabPat!);
    await kubectl(["create", "namespace", "gitlab-runner"]).catch(() => undefined);
    if (!(await tokenSecretExists())) {
      const token = await gitlab.createInstanceRunner(RUNNER_NAME);
      await applyYaml(JSON.stringify({
        apiVersion: "v1",
        kind: "Secret",
        metadata: { name: "gitlab-runner-token", namespace: "gitlab-runner" },
        stringData: { "runner-registration-token": "", "runner-token": token },
      }));
    }
    await helmUpgrade({
      release: "gitlab-runner",
      chart: "gitlab/gitlab-runner",
      version: VERSIONS.gitlabRunnerChart,
      ns: "gitlab-runner",
      repo: { name: "gitlab", url: "https://charts.gitlab.io" },
      values: asset("values/gitlab-runner.yaml", { arch: ctx.arch }),
    });
    await waitFor("GitLab Runner to come online", async () => {
      const online = await gitlab.onlineRunners();
      return { ok: online.some((r) => r.description === RUNNER_NAME), state: `${online.length} online` };
    }, 5 * 60_000);
  },
};
