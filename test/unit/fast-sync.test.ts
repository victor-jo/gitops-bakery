// Tests for the fast-sync setup: a narrow Argo CD "ci" account and the recorded mode
import { expect, test } from "vitest";
import { parse } from "yaml";
import { asset } from "../../src/lib/assets.js";
import { saveState, loadState } from "../../src/lib/state.js";
import { getFastSyncMode } from "../../src/steps/fast-sync.js";
import { useTempHome } from "../helpers/home.js";

useTempHome();

test("Argo CD gets an API-key-only ci account that can only read applications", () => {
  const v = parse(asset("values/argocd.yaml"));
  expect(v.configs.cm["accounts.ci"]).toBe("apiKey");
  expect(v.configs.rbac["policy.csv"]).toContain("p, role:ci, applications, get, */*, allow");
  expect(v.configs.rbac["policy.csv"]).toContain("g, ci, role:ci");
});

test("getFastSyncMode refuses to guess before the fast-sync step ran", () => {
  expect(() => getFastSyncMode()).toThrow(/fast-sync/);
  saveState({ ...loadState(), fastSync: "ci-refresh" });
  expect(getFastSyncMode()).toBe("ci-refresh");
});
