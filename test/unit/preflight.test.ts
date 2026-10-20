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
