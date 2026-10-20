// Installs GitLab CE and publishes it on host port 80 through a fixed NodePort service
import { GITLAB_HOST_URL, GITLAB_NODE_PORT, VERSIONS } from "../lib/config.js";
import { asset } from "../lib/assets.js";
import { helmUpgrade } from "../lib/helm.js";
import { applyYaml, kubectl } from "../lib/kube.js";
import { waitFor } from "../lib/wait.js";
import type { Step } from "./types.js";

export const gitlabStep: Step = {
  id: "gitlab",
  title: "GitLab",
  async run() {
    await helmUpgrade({
      release: "gitlab",
      chart: "gitlab/gitlab",
      version: VERSIONS.gitlabChart,
      ns: "gitlab",
      repo: { name: "gitlab", url: "https://charts.gitlab.io" },
      values: asset("values/gitlab.yaml"),
      timeout: "25m",
    });
    // The chart cannot pin a NodePort, so reuse the webservice selector on a service we own
    const selector = await kubectl(["-n", "gitlab", "get", "svc", "gitlab-webservice-default", "-o", "jsonpath={.spec.selector}"]);
    await applyYaml(asset("deps/gitlab-host-service.yaml", { selector, nodePort: GITLAB_NODE_PORT }));
    await waitFor("GitLab readiness on http://localhost", async () => {
      const r = await fetch(`${GITLAB_HOST_URL}/-/readiness`);
      return { ok: r.ok, state: `HTTP ${r.status}` };
    }, 10 * 60_000);
  },
};
