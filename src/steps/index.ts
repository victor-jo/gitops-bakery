// Install order of all steps
import { clusterStep } from "./cluster.js";
import { preflightStep } from "./preflight.js";
import type { Step } from "./types.js";

export const ALL_STEPS: Step[] = [preflightStep, clusterStep];
