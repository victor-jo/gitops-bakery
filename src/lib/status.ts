// Collects pod readiness per namespace for the CLI status command and the MCP status tool
import { run } from "./exec.js";
import { kubeContext } from "./kube.js";
import { clusterName } from "./names.js";

export type StatusReport = { cluster: string; reachable?: boolean; components: { namespace: string; ready: number; total: number }[] };

export async function statusReport(): Promise<StatusReport> {
  const res = await run("kubectl", ["--context", kubeContext(), "get", "pods", "-A", "--no-headers"], { allowFail: true });
  if (res.code !== 0) return { cluster: clusterName(), reachable: false, components: [] };
  const byNs = new Map<string, { ready: number; total: number }>();
  for (const line of res.stdout.trim().split("\n").filter(Boolean)) {
    const [ns, , , status] = line.split(/\s+/);
    const e = byNs.get(ns) ?? { ready: 0, total: 0 };
    e.total++;
    if (status === "Running" || status === "Completed") e.ready++;
    byNs.set(ns, e);
  }
  return { cluster: clusterName(), reachable: true, components: [...byNs].map(([namespace, e]) => ({ namespace, ...e })) };
}
