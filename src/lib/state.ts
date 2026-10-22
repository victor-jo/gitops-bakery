// Install progress and created apps, persisted in ~/.gitops-bakery/state.json
import { join } from "node:path";
import { readJson, writeJsonAtomic } from "./fsutil.js";
import { bakeryHome } from "./paths.js";
import { randomClusterName } from "./names.js";

export type AppRecord = { name: string; nodePort: number; createdAt: string };

export type State = {
  version: 1;
  clusterName: string;
  steps: Record<string, { doneAt: string }>;
  apps: Record<string, AppRecord>;
  fastSync?: "webhook" | "ci-refresh";
};

const statePath = () => join(bakeryHome(), "state.json");

// Read-only view for commands that must not create a lab as a side effect (uninstall)
export function readState(): State | undefined {
  return readJson<State>(statePath());
}

export function loadState(): State {
  const existing = readJson<State>(statePath());
  if (existing) return existing;
  const fresh: State = { version: 1, clusterName: randomClusterName(), steps: {}, apps: {} };
  saveState(fresh);
  return fresh;
}

export function saveState(s: State): void {
  writeJsonAtomic(statePath(), s);
}

export function markDone(id: string): void {
  const s = loadState();
  s.steps[id] = { doneAt: new Date().toISOString() };
  saveState(s);
}

export function isDone(id: string): boolean {
  return id in loadState().steps;
}
