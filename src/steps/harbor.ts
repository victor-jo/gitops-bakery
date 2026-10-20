// Installs Harbor and prepares the public "apps" project with a push/pull robot for CI
import { HARBOR_HOST_URL, VERSIONS } from "../lib/config.js";
import { asset } from "../lib/assets.js";
import { Harbor } from "../lib/harbor.js";
import { helmUpgrade } from "../lib/helm.js";
import { registryHost } from "../lib/names.js";
import { updateSecrets } from "../lib/secrets.js";
import { waitFor } from "../lib/wait.js";
import type { Step } from "./types.js";

export const HARBOR_APPS_PROJECT = "apps";
export const HARBOR_ROBOT = "ci";

export const harborStep: Step = {
  id: "harbor",
  title: "Harbor",
  async run(ctx) {
    await helmUpgrade({
      release: "harbor",
      chart: "harbor/harbor",
      version: VERSIONS.harborChart,
      ns: "harbor",
      repo: { name: "harbor", url: "https://helm.goharbor.io" },
      values: asset("values/harbor.yaml", { registry: registryHost(), harborAdmin: ctx.secrets.harborAdmin }),
      timeout: "15m",
    });
    await waitFor("Harbor API", async () => {
      const r = await fetch(`${HARBOR_HOST_URL}/api/v2.0/health`);
      return { ok: r.ok, state: `HTTP ${r.status}` };
    }, 10 * 60_000);
    const harbor = new Harbor(HARBOR_HOST_URL, "admin", ctx.secrets.harborAdmin);
    await harbor.ensureProject(HARBOR_APPS_PROJECT, true);
    const robot = await harbor.ensureRobot(HARBOR_APPS_PROJECT, HARBOR_ROBOT);
    ctx.secrets = updateSecrets({ harborRobotSecret: robot.secret });
  },
};
