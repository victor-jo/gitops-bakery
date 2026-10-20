// Points GITOPS_BAKERY_HOME at a fresh temp directory for each test
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach } from "vitest";

export function useTempHome(): () => string {
  let dir = "";
  beforeEach(() => {
    dir = mkdtempSync(join(tmpdir(), "bakery-test-"));
    process.env.GITOPS_BAKERY_HOME = dir;
  });
  afterEach(() => {
    delete process.env.GITOPS_BAKERY_HOME;
    rmSync(dir, { recursive: true, force: true });
  });
  return () => dir;
}
