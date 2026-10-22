// Tests for the process runner's error messages
import { expect, test } from "vitest";
import { run } from "../../src/lib/exec.js";

test("ExecError masks redacted values in the command line and stderr", async () => {
  const err = await run("sh", ["-c", 'echo "bad token $0" >&2; exit 3', "SECRET123"], { redact: ["SECRET123"] }).catch((e: Error) => e);
  expect(err).toBeInstanceOf(Error);
  expect((err as Error).message).not.toContain("SECRET123");
  expect((err as Error).message).toContain("***");
});
