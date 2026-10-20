// Tests for preflight port checks
import { expect, test } from "vitest";
import { checkPorts, portProblems } from "../../src/steps/preflight.js";

test("checkPorts returns only the busy ports", async () => {
  expect(await checkPorts(async (p) => p !== 30001)).toEqual([30001]);
});

test("preflight reports busy ports", async () => {
  const problems = portProblems([30001]);
  expect(problems.join("\n")).toContain("30001");
});

test("only EADDRINUSE counts as busy; EACCES on port 80 does not", async () => {
  const { bindErrorMeansBusy } = await import("../../src/steps/preflight.js");
  expect(bindErrorMeansBusy("EADDRINUSE")).toBe(true);
  expect(bindErrorMeansBusy("EACCES")).toBe(false);
});
