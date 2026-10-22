// kubectl wrapper pinned to this lab's kind context so other clusters are never touched
import { run } from "./exec.js";
import { clusterName } from "./names.js";

export function kubeContext(): string {
  return `kind-${clusterName()}`;
}

export async function kubectl(args: string[], input?: string, redact: string[] = []): Promise<string> {
  return (await run("kubectl", ["--context", kubeContext(), ...args], { input, redact })).stdout;
}

export async function applyYaml(yaml: string, opts: { serverSide?: boolean } = {}): Promise<void> {
  await kubectl(["apply", ...(opts.serverSide ? ["--server-side", "--force-conflicts"] : []), "-f", "-"], yaml);
}

export async function secretValue(ns: string, name: string, key: string): Promise<string> {
  const b64 = await kubectl(["-n", ns, "get", "secret", name, "-o", `jsonpath={.data.${key.replace(/\./g, "\\.")}}`]);
  return Buffer.from(b64.trim(), "base64").toString("utf8");
}
