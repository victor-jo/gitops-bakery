// Tests for the idempotent step runner and the readiness wait helper
import { expect, test, vi } from "vitest";
import type { Logger } from "../../src/lib/log.js";
import { markDone } from "../../src/lib/state.js";
import { waitFor } from "../../src/lib/wait.js";
import { runSteps } from "../../src/steps/runner.js";
import type { Ctx, Step } from "../../src/steps/types.js";
import { useTempHome } from "../helpers/home.js";

useTempHome();

const log: Logger = { info: () => {}, step: () => {} };
const ctx = { secrets: {}, log, arch: "arm64" } as unknown as Ctx;
const step = (id: string, run = vi.fn(async () => {})): Step & { run: ReturnType<typeof vi.fn> } => ({ id, title: id, run });

test("runner skips done steps", async () => {
  const a = step("a");
  const b = step("b");
  markDone("a");
  await runSteps([a, b], ctx);
  expect(a.run).not.toHaveBeenCalled();
  expect(b.run).toHaveBeenCalledTimes(1);
});

test("runner resumes after a failed step", async () => {
  const a = step("a");
  const b = step("b", vi.fn().mockRejectedValueOnce(new Error("boom")).mockResolvedValue(undefined));
  const c = step("c");
  await expect(runSteps([a, b, c], ctx)).rejects.toThrow("boom");
  expect(c.run).not.toHaveBeenCalled();
  await runSteps([a, b, c], ctx);
  expect(a.run).toHaveBeenCalledTimes(1);
  expect(b.run).toHaveBeenCalledTimes(2);
  expect(c.run).toHaveBeenCalledTimes(1);
});

test("force reruns done steps", async () => {
  const a = step("a");
  markDone("a");
  await runSteps([a], ctx, { force: true });
  expect(a.run).toHaveBeenCalledTimes(1);
});

test("waitFor reports last state on timeout", async () => {
  await expect(waitFor("harbor core", async () => ({ ok: false, state: "Pending" }), 30, 10)).rejects.toThrow(
    /harbor core.*Pending/,
  );
});
