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
import { bakeryHome, packageVersion } from "./lib/paths.js";
import { loadOrCreateSecrets, secretsPath } from "./lib/secrets.js";
import { ALL_STEPS } from "./steps/index.js";
import { preflight } from "./steps/preflight.js";
import { doctorSummary, pickUninstallTarget } from "./uninstall.js";
import { readState } from "./lib/state.js";
import { removeClaudeIntegration } from "./steps/claude.js";
import { startMcpServer } from "./mcp/server.js";
import { statusReport } from "./lib/status.js";
import { runSteps } from "./steps/runner.js";

const program = new Command()
  .name("gitops-bakery")
  .description("One-command GitOps lab on kind, wired to Claude Code through a skill and an MCP server")
  .version(packageVersion());

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
    const report = await statusReport();
    console.log(`Cluster: ${report.cluster} (context ${kubeContext()})`);
    if (!report.reachable) console.log("  cluster is not reachable");
    for (const c of report.components) console.log(`  ${c.namespace.padEnd(20)} ${c.ready}/${c.total} running`);
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
    const state = readState();
    const running = state && (await kindClusters()).includes(state.clusterName) ? state.clusterName : undefined;
    console.log(doctorSummary(report, running));
    if (!report.ok) process.exitCode = 1;
  });

program
  .command("uninstall")
  .description("Delete the cluster and everything gitops-bakery stored on this machine")
  .option("--yes", "do not ask for confirmation")
  .option("--cluster <name>", "cluster to delete when ~/.gitops-bakery/state.json is missing")
  .action(async (opts: { yes?: boolean; cluster?: string }) => {
    const pick = pickUninstallTarget({ stateName: readState()?.clusterName, explicit: opts.cluster, clusters: await kindClusters() });
    if (pick.error) {
      console.log(pick.error);
      process.exitCode = 1;
      return;
    }
    const name = pick.target!;
    if (pick.guessed) console.log(`state.json is missing; ${name} is the only cluster with a gitops-bakery name.`);
    if (!opts.yes) {
      const rl = createInterface({ input: process.stdin, output: process.stdout });
      const answer = await rl.question(`Delete cluster ${name} and ${bakeryHome()}? [y/N] `);
      rl.close();
      if (answer.trim().toLowerCase() !== "y") return;
    }
    await run("kind", ["delete", "cluster", "--name", name]);
    await removeClaudeIntegration();
    if (existsSync(bakeryHome())) rmSync(bakeryHome(), { recursive: true, force: true });
    console.log(`✓ Removed ${name}`);
  });

async function kindClusters(): Promise<string[]> {
  const res = await run("kind", ["get", "clusters"], { allowFail: true });
  return res.code === 0 ? res.stdout.split("\n").filter(Boolean) : [];
}

program
  .command("mcp")
  .description("Run the MCP server on stdio (used by Claude Code)")
  .action(async () => {
    await startMcpServer();
  });

program.parseAsync().catch((e: Error) => {
  console.error(`\n${e.message}`);
  process.exit(1);
});
