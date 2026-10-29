// Install order of all steps
import { argocdStep } from "./argocd.js";
import { bootstrapStep, serviceRootAllowEmptyStep } from "./bootstrap.js";
import { claudeStep } from "./claude.js";
import { clusterStep } from "./cluster.js";
import { cnpgStep } from "./cnpg.js";
import { fastSyncStep } from "./fast-sync.js";
import { garageStep } from "./garage.js";
import { gitlabAuthStep } from "./gitlab-auth.js";
import { gitlabRunnerStep } from "./gitlab-runner.js";
import { gitlabStep } from "./gitlab.js";
import { valkeyStep } from "./valkey.js";
import { harborStep } from "./harbor.js";
import { preflightStep } from "./preflight.js";
import { ML_STEPS } from "./ml/index.js";
import type { Step } from "./types.js";

export const ALL_STEPS: Step[] = [preflightStep, clusterStep, harborStep, argocdStep, cnpgStep, valkeyStep, garageStep, gitlabStep, gitlabAuthStep, gitlabRunnerStep, bootstrapStep, serviceRootAllowEmptyStep, fastSyncStep, claudeStep];

// The ML layer goes last, so a failure there still leaves a working base lab and Claude integration
export function installSteps(ml: boolean): Step[] {
  return ml ? [...ALL_STEPS, ...ML_STEPS] : ALL_STEPS;
}
