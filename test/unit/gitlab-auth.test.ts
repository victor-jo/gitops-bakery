// Tests that the root token is minted without ever appearing in a command line
import { expect, test } from "vitest";
import { mintRootToken } from "../../src/steps/gitlab-auth.js";

test("PAT step never puts the token in argv", async () => {
  const calls: { args: string[]; input?: string }[] = [];
  await mintRootToken("glpat-TOPSECRETTOKEN0000", async (args, input) => {
    calls.push({ args, input });
    return "";
  });
  expect(calls.length).toBeGreaterThan(0);
  for (const c of calls) expect(c.args.join(" ")).not.toContain("TOPSECRET");
  expect(calls.some((c) => c.input?.includes("glpat-TOPSECRETTOKEN0000"))).toBe(true);
});
