#!/usr/bin/env node
// Command-line entry: install, status, credentials, doctor, uninstall and the MCP server
import { existsSync, rmSync } from "node:fs";
import { createInterface } from "node:readline/promises";
import { Command } from "commander";
import { ARGOCD_HOST_URL, GITLAB_HOST_URL, GRAFANA_HOST_URL, HARBOR_HOST_URL } from "./lib/config.js";
import { run } from "./lib/exec.js";
import { consoleLogger } from "./lib/log.js";
import { kubeContext } from "./lib/kube.js";
import { clusterName } from "./lib/names.js";
import { bakeryHome } from "./lib/paths.js";
import { loadOrCreateSecrets, secretsPath } from "./lib/secrets.js";
import { ALL_STEPS } from "./steps/index.js";
import { preflight } from "./steps/preflight.js";
import { runSteps } from "./steps/runner.js";

const program = new Command()
  .name("gitops-bakery")
  .description("One-command GitOps lab on kind, wired to Claude Code through a skill and an MCP server")
  .version("0.1.0");

const ENDPOINTS = [
  ["GitLab", GITLAB_HOST_URL, "root"],
  ["Harbor", HARBOR_HOST_URL, "admin"],
  ["Argo CD", ARGOCD_HOST_URL, "admin"],
  ["Grafana", GRAFANA_HOST_URL, "admin"],
] as const;

program
  .command("install")
  .description("Create the kind cluster and install the whole stack (safe to rerun)")
  .option("--force", "rerun steps that are already done")
  .action(async (opts: { force?: boolean }) => {
    const ctx = { secrets: loadOrCreateSecrets(), log: consoleLogger, arch: process.arch === "arm64" ? "arm64" : "amd64" } as const;
    console.log(`Cluster: ${clusterName()}`);
    await runSteps(ALL_STEPS, ctx, { force: opts.force });
    console.log("\nDone. Endpoints:");
    for (const [name, url] of ENDPOINTS) console.log(`  ${name.padEnd(8)} ${url}`);
  });

program
  .command("status")
  .description("Show pod readiness per namespace and the lab URLs")
  .action(async () => {
    console.log(`Cluster: ${clusterName()} (context ${kubeContext()})`);
    const res = await run("kubectl", ["--context", kubeContext(), "get", "pods", "-A", "--no-headers"], { allowFail: true });
    if (res.code !== 0) {
      console.log("  cluster is not reachable");
      return;
    }
    const byNs = new Map<string, { ready: number; total: number }>();
    for (const line of res.stdout.trim().split("\n").filter(Boolean)) {
      const [ns, , , status] = line.split(/\s+/);
      const entry = byNs.get(ns) ?? { ready: 0, total: 0 };
      entry.total++;
      if (status === "Running" || status === "Completed") entry.ready++;
      byNs.set(ns, entry);
    }
    for (const [ns, e] of byNs) console.log(`  ${ns.padEnd(20)} ${e.ready}/${e.total} running`);
    for (const [name, url] of ENDPOINTS) console.log(`  ${name.padEnd(8)} ${url}`);
  });

program
  .command("credentials")
  .description("Show usernames and where the generated passwords are stored")
  .action(() => {
    for (const [name, url, user] of ENDPOINTS) console.log(`  ${name.padEnd(8)} ${url}  user: ${user}`);
    console.log(`\nPasswords are in ${secretsPath()} (readable only by you).`);
  });

program
  .command("doctor")
  .description("Check Docker, required CLIs, memory and free ports")
  .action(async () => {
    const report = await preflight();
    if (report.ok) console.log("✓ Ready to install");
    else {
      for (const p of report.problems) console.log(`✗ ${p}`);
      process.exitCode = 1;
    }
  });

program
  .command("uninstall")
  .description("Delete the cluster and everything gitops-bakery stored on this machine")
  .option("--yes", "do not ask for confirmation")
  .action(async (opts: { yes?: boolean }) => {
    const name = clusterName();
    if (!opts.yes) {
      const rl = createInterface({ input: process.stdin, output: process.stdout });
      const answer = await rl.question(`Delete cluster ${name} and ${bakeryHome()}? [y/N] `);
      rl.close();
      if (answer.trim().toLowerCase() !== "y") return;
    }
    await run("kind", ["delete", "cluster", "--name", name]);
    if (existsSync(bakeryHome())) rmSync(bakeryHome(), { recursive: true, force: true });
    console.log(`✓ Removed ${name}`);
  });

program
  .command("mcp")
  .description("Run the MCP server on stdio (used by Claude Code)")
  .action(async () => {
    throw new Error("MCP server is not available yet");
  });

program.parseAsync().catch((e: Error) => {
  console.error(`\n${e.message}`);
  process.exit(1);
});
