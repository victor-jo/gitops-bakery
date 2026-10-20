// Install order of all steps
import { argocdStep } from "./argocd.js";
import { clusterStep } from "./cluster.js";
import { harborStep } from "./harbor.js";
import { preflightStep } from "./preflight.js";
import type { Step } from "./types.js";

export const ALL_STEPS: Step[] = [preflightStep, clusterStep, harborStep, argocdStep];
