// kubectl wrapper pinned to this lab's kind context so other clusters are never touched
import { run } from "./exec.js";
import { clusterName } from "./names.js";

export function kubeContext(): string {
  return `kind-${clusterName()}`;
}

export async function kubectl(args: string[], input?: string): Promise<string> {
  return (await run("kubectl", ["--context", kubeContext(), ...args], { input })).stdout;
}
