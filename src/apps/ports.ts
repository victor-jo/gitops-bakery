// Hands out host ports for apps from the fixed 30010-30019 pool
import { PORTS } from "../lib/config.js";
import type { AppRecord } from "../lib/state.js";

export function allocatePort(apps: Record<string, AppRecord>): number {
  const used = new Set(Object.values(apps).map((a) => a.nodePort));
  for (let p = PORTS.appMin; p <= PORTS.appMax; p++) if (!used.has(p)) return p;
  throw new Error(`No free app port (${PORTS.appMin}-${PORTS.appMax} are all used); delete an app first`);
}
