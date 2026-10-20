// Installs Valkey as GitLab's Redis with a generated password
import { VERSIONS } from "../lib/config.js";
import { asset } from "../lib/assets.js";
import { helmUpgrade } from "../lib/helm.js";
import type { Step } from "./types.js";

export const valkeyStep: Step = {
  id: "valkey",
  title: "Redis (Valkey)",
  async run(ctx) {
    await helmUpgrade({
      release: "valkey",
      chart: "valkey/valkey",
      version: VERSIONS.valkeyChart,
      ns: "gitlab",
      repo: { name: "valkey", url: "https://valkey.io/valkey-helm/" },
      values: asset("values/valkey.yaml", { valkey: ctx.secrets.valkey }),
    });
  },
};
