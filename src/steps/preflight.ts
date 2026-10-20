// Checks the host before anything is created: Docker, CLIs, memory and free ports
import { createServer } from "node:net";
import { PORTS } from "../lib/config.js";
import { run } from "../lib/exec.js";
import type { Step } from "./types.js";

export type PreflightReport = { ok: boolean; problems: string[] };

const REQUIRED_TOOLS = ["kind", "helm", "kubectl", "git"];
const MIN_MEMORY_BYTES = 10 * 1024 ** 3;

export function labPorts(): number[] {
  const ports: number[] = [PORTS.gitlab, PORTS.harbor, PORTS.argocd, PORTS.grafana];
  for (let p = PORTS.appMin; p <= PORTS.appMax; p++) ports.push(p);
  return ports;
}

export function isPortFree(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const server = createServer();
    server.once("error", () => resolve(false));
    server.listen(port, "127.0.0.1", () => server.close(() => resolve(true)));
  });
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

export async function preflight(opts: { skipPorts?: boolean } = {}): Promise<PreflightReport> {
  const problems: string[] = [];
  const info = await run("docker", ["info", "--format", "{{.MemTotal}}"], { allowFail: true }).catch(() => undefined);
  if (!info || info.code !== 0) problems.push("Docker is not reachable; start OrbStack or Docker Desktop");
  else if (Number(info.stdout.trim()) < MIN_MEMORY_BYTES)
    problems.push(`Docker has ${(Number(info.stdout) / 1024 ** 3).toFixed(1)} GiB memory; at least 10 GiB is needed`);
  for (const tool of REQUIRED_TOOLS) if (!(await onPath(tool))) problems.push(`'${tool}' is not on PATH (brew install ${tool === "kubectl" ? "kubernetes-cli" : tool})`);
  if (!opts.skipPorts) problems.push(...portProblems(await checkPorts()));
  return { ok: problems.length === 0, problems };
}

export const preflightStep: Step = {
  id: "preflight",
  title: "Preflight checks",
  async run() {
    const report = await preflight();
    if (!report.ok) throw new Error(`Preflight failed:\n- ${report.problems.join("\n- ")}`);
  },
};
