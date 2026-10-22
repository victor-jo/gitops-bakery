// Installs the gitops-bakery skill and registers the MCP server with Claude Code at user scope
import { cpSync, existsSync, readFileSync, rmSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { run } from "../lib/exec.js";
import { packageRoot, packageVersion } from "../lib/paths.js";
import type { Step } from "./types.js";

const SERVER_NAME = "gitops-bakery";

export function claudeHome(): string {
  return process.env.CLAUDE_CONFIG_DIR ?? join(homedir(), ".claude");
}

function skillDir(): string {
  return join(claudeHome(), "skills", SERVER_NAME);
}

// A checkout runs its own build; an npx install pins the same tag so MCP code matches the installed lab
export function mcpCommand(): { command: string; args: string[] } {
  if (existsSync(join(packageRoot(), ".git"))) return { command: "node", args: [join(packageRoot(), "dist", "cli.js"), "mcp"] };
  const { version } = JSON.parse(readFileSync(join(packageRoot(), "package.json"), "utf8")) as { version: string };
  return { command: "npx", args: ["-y", `github:victor-jo/gitops-bakery#v${version}`, "mcp"] };
}

// Quotes only what a POSIX shell would split or expand, so the printed command can be pasted as is
export function shellQuote(args: string[]): string {
  return args.map((a) => (/^[A-Za-z0-9@%+=:,./_-]+$/.test(a) ? a : `'${a.replace(/'/g, "'\\''")}'`)).join(" ");
}

async function hasClaude(): Promise<boolean> {
  return (await run("which", ["claude"], { allowFail: true })).code === 0;
}

// The id carries the version so upgrading the CLI re-registers the MCP entry and skill, which are pinned per release
export const claudeStep: Step = {
  id: `claude@${packageVersion()}`,
  title: "Claude Code skill and MCP server",
  async run(ctx) {
    rmSync(skillDir(), { recursive: true, force: true });
    cpSync(join(packageRoot(), "skills", SERVER_NAME), skillDir(), { recursive: true });
    const { command, args } = mcpCommand();
    const addArgs = ["mcp", "add", "--scope", "user", SERVER_NAME, "--", command, ...args];
    if (!(await hasClaude())) {
      ctx.log.info(`Claude Code not found. Skill installed in ${skillDir()}. Register the MCP server later with:`);
      ctx.log.info(`  claude ${shellQuote(addArgs)}`);
      return;
    }
    await run("claude", ["mcp", "remove", "--scope", "user", SERVER_NAME], { allowFail: true });
    await run("claude", addArgs);
    ctx.log.info(`Registered MCP server "${SERVER_NAME}" and installed the skill in ${skillDir()}`);
  },
};

export async function removeClaudeIntegration(): Promise<void> {
  rmSync(skillDir(), { recursive: true, force: true });
  if (await hasClaude()) await run("claude", ["mcp", "remove", "--scope", "user", SERVER_NAME], { allowFail: true });
}
