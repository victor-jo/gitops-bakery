// Runs install steps in order, skipping finished ones so a rerun resumes after a failure
import { isDone, markDone } from "../lib/state.js";
import type { Ctx, Step } from "./types.js";

export async function runSteps(steps: Step[], ctx: Ctx, opts: { force?: boolean } = {}): Promise<void> {
  for (const step of steps) {
    if (!opts.force && isDone(step.id)) {
      ctx.log.step(step.title, "skipped");
      continue;
    }
    ctx.log.step(step.title, "start");
    try {
      await step.run(ctx);
    } catch (e) {
      ctx.log.step(step.title, "failed");
      throw e;
    }
    markDone(step.id);
    ctx.log.step(step.title, "done");
  }
}
