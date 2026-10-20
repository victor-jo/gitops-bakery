// Tests for the Claude Code integration: skill install, MCP registration command and the no-claude fallback
import { existsSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, expect, test } from "vitest";
import { claudeStep, mcpCommand } from "../../src/steps/claude.js";
import type { Ctx } from "../../src/steps/types.js";
import { useTempHome } from "../helpers/home.js";

useTempHome();
let claudeDir = "";
const savedPath = process.env.PATH;
beforeEach(() => {
  claudeDir = mkdtempSync(join(tmpdir(), "bakery-claude-"));
  process.env.CLAUDE_CONFIG_DIR = claudeDir;
});
afterEach(() => {
  delete process.env.CLAUDE_CONFIG_DIR;
  process.env.PATH = savedPath;
});

test("from a git checkout the MCP entry runs the local build", () => {
  const cmd = mcpCommand();
  expect(cmd.command).toBe("node");
  expect(cmd.args[0]).toMatch(/dist\/cli\.js$/);
  expect(cmd.args[1]).toBe("mcp");
});

test("without the claude CLI the step installs the skill, prints the command and still succeeds", async () => {
  process.env.PATH = "/usr/bin:/bin";
  const lines: string[] = [];
  const ctx = { log: { info: (m: string) => lines.push(m), step: () => {} } } as unknown as Ctx;
  await claudeStep.run(ctx);
  expect(existsSync(join(claudeDir, "skills", "gitops-bakery", "SKILL.md"))).toBe(true);
  expect(lines.join("\n")).toContain("claude mcp add --scope user gitops-bakery --");
});
