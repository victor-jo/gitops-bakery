// Tests for finding the cluster to uninstall without ever inventing one, and for doctor's wording on a running lab
import { existsSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "vitest";
import { doctorSummary, pickUninstallTarget } from "../../src/uninstall.js";
import { isBakeryClusterName } from "../../src/lib/names.js";
import { readState } from "../../src/lib/state.js";
import { useTempHome } from "../helpers/home.js";

const home = useTempHome();

test("readState never creates state.json", () => {
  expect(readState()).toBeUndefined();
  expect(existsSync(join(home(), "state.json"))).toBe(false);
});

test("bakery names are recognised and other kind clusters are not", () => {
  expect(isBakeryClusterName("toasty-scone")).toBe(true);
  expect(isBakeryClusterName("kind")).toBe(false);
  expect(isBakeryClusterName("ml-k8s")).toBe(false);
});

test("pickUninstallTarget prefers state, then an explicit name, then a single bakery-looking cluster", () => {
  expect(pickUninstallTarget({ stateName: "airy-scone", clusters: ["airy-scone", "kind"] })).toEqual({ target: "airy-scone" });
  expect(pickUninstallTarget({ explicit: "kind", clusters: ["kind"] })).toEqual({ target: "kind" });
  expect(pickUninstallTarget({ clusters: ["kind", "toasty-scone"] })).toEqual({ target: "toasty-scone", guessed: true });
});

test("pickUninstallTarget refuses to guess between several or invent one", () => {
  expect(pickUninstallTarget({ clusters: ["toasty-scone", "golden-danish"] }).error).toMatch(/--cluster/);
  expect(pickUninstallTarget({ clusters: ["kind", "ml-k8s"] }).error).toMatch(/No gitops-bakery cluster/);
  expect(pickUninstallTarget({ explicit: "nope", clusters: ["kind"] }).error).toMatch(/nope/);
});

test("doctor message reflects a running lab", () => {
  expect(doctorSummary({ ok: true, problems: [] }, "toasty-scone")).toMatch(/toasty-scone is running/);
  expect(doctorSummary({ ok: true, problems: [] }, undefined)).toMatch(/Ready to install/);
});
