// Checks the host before anything is created: Docker, CLIs, memory and free ports
import { createServer } from "node:net";
import { PORTS } from "../lib/config.js";
import { run } from "../lib/exec.js";
import { clusterName } from "../lib/names.js";
import type { Step } from "./types.js";

export type PreflightReport = { ok: boolean; problems: string[] };

const REQUIRED_TOOLS = ["kind", "helm", "kubectl", "git"];
const MIN_MEMORY_BYTES = 10 * 1024 ** 3;
// The ML layer measured about 11.6 GiB across the four nodes; Docker on a 16 GiB machine reports roughly 15.7 GiB
const MIN_ML_MEMORY_BYTES = 14 * 1024 ** 3;

export function minMemoryBytes(ml: boolean): number {
  return ml ? MIN_ML_MEMORY_BYTES : MIN_MEMORY_BYTES;
}

// cloud-provider-kind runs on the host as root (it binds LoadBalancer IPs on lo0), so the installer can only check for it
export const CLOUD_PROVIDER_KIND_HINT =
  "cloud-provider-kind is not running; install it with 'brew install cloud-provider-kind' and keep 'sudo cloud-provider-kind' running in another terminal";

async function cloudProviderKindRunning(): Promise<boolean> {
  return (await run("pgrep", ["-x", "cloud-provider-kind"], { allowFail: true })).code === 0;
}

export function labPorts(): number[] {
  const ports: number[] = [PORTS.gitlab, PORTS.harbor, PORTS.argocd, PORTS.grafana];
  for (let p = PORTS.appMin; p <= PORTS.appMax; p++) ports.push(p);
  return ports;
}

// macOS refuses unprivileged binds below 1024 with EACCES, yet Docker can still publish them,
// so only "address in use" means another process holds the port
export function bindErrorMeansBusy(code: string | undefined): boolean {
  return code === "EADDRINUSE";
}

function canBind(port: number, host: string): Promise<boolean> {
  return new Promise((resolve) => {
    const server = createServer();
    server.once("error", (e: NodeJS.ErrnoException) => resolve(!bindErrorMeansBusy(e.code)));
    server.listen(port, host, () => server.close(() => resolve(true)));
  });
}

// A listener on 0.0.0.0 or :: does not stop a bind to 127.0.0.1 on macOS, so every address family is tried
export async function isPortFree(port: number): Promise<boolean> {
  for (const host of ["127.0.0.1", "0.0.0.0", "::"]) if (!(await canBind(port, host))) return false;
  return true;
}

// The lab's own cluster holds every lab port, so checking them again (install --force, doctor) would always fail
export function shouldCheckPorts(existingClusters: string[], name: string): boolean {
  return !existingClusters.includes(name);
}

async function kindClusters(): Promise<string[]> {
  const res = await run("kind", ["get", "clusters"], { allowFail: true }).catch(() => undefined);
  return res?.code === 0 ? res.stdout.split("\n").filter(Boolean) : [];
}

export async function checkPorts(isFree: (port: number) => Promise<boolean> = isPortFree): Promise<number[]> {
  const busy: number[] = [];
  for (const port of labPorts()) if (!(await isFree(port))) busy.push(port);
  return busy;
}

export function portProblems(busy: number[]): string[] {
  return busy.map((p) => `Port ${p} on 127.0.0.1 is already in use; free it before installing`);
}

async function onPath(tool: string): Promise<boolean> {
  return (await run("which", [tool], { allowFail: true })).code === 0;
}

export async function preflight(opts: { skipPorts?: boolean; ml?: boolean } = {}): Promise<PreflightReport> {
  const problems: string[] = [];
  const min = minMemoryBytes(Boolean(opts.ml));
  const info = await run("docker", ["info", "--format", "{{.MemTotal}}"], { allowFail: true }).catch(() => undefined);
  if (!info || info.code !== 0) problems.push("Docker is not reachable; start OrbStack or Docker Desktop");
  else if (Number(info.stdout.trim()) < min)
    problems.push(`Docker has ${(Number(info.stdout) / 1024 ** 3).toFixed(1)} GiB memory; at least ${min / 1024 ** 3} GiB is needed${opts.ml ? " with --with-ml" : ""}`);
  for (const tool of REQUIRED_TOOLS) if (!(await onPath(tool))) problems.push(`'${tool}' is not on PATH (brew install ${tool === "kubectl" ? "kubernetes-cli" : tool})`);
  if (opts.ml && !(await cloudProviderKindRunning())) problems.push(CLOUD_PROVIDER_KIND_HINT);
  if (!opts.skipPorts && shouldCheckPorts(await kindClusters(), clusterName())) problems.push(...portProblems(await checkPorts()));
  return { ok: problems.length === 0, problems };
}

export const preflightStep: Step = {
  id: "preflight",
  title: "Preflight checks",
  async run(ctx) {
    const report = await preflight({ ml: ctx.ml });
    if (!report.ok) throw new Error(`Preflight failed:\n- ${report.problems.join("\n- ")}`);
  },
};
