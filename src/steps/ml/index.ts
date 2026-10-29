// Install order of the optional ML layer, appended after the base lab when install runs with --with-ml
import { preflight } from "../preflight.js";
import type { Step } from "../types.js";
import { mlGatewaysStep } from "./gateways.js";
import { mlKfpImageStep } from "./kfp-image.js";
import { mlPlatformStep } from "./platform.js";
import { mlSeedStep } from "./seed.js";
import { mlStorageStep } from "./storage.js";

// A lab installed without --with-ml has its preflight marked done, so the ML checks get a step of their own
export const mlPreflightStep: Step = {
  id: "ml-preflight",
  title: "ML preflight (memory, cloud-provider-kind)",
  async run() {
    const report = await preflight({ skipPorts: true, ml: true });
    if (!report.ok) throw new Error(`Preflight failed:\n- ${report.problems.join("\n- ")}`);
  },
};

export const ML_STEPS: Step[] = [mlPreflightStep, mlStorageStep, mlGatewaysStep, mlPlatformStep, mlSeedStep, mlKfpImageStep];
