// Regression tests for issues found in the v0.1.1 review
import { expect, test, vi } from "vitest";
import { deleteApp, type AppDeps } from "../../src/apps/lifecycle.js";
import { packageVersion } from "../../src/lib/paths.js";
import { loadState, saveState } from "../../src/lib/state.js";
import { commitIfChanged } from "../../src/steps/bootstrap.js";
import { claudeStep } from "../../src/steps/claude.js";
import { pickUninstallTarget } from "../../src/uninstall.js";
import { useTempHome } from "../helpers/home.js";

useTempHome();

test("upgrading the CLI re-registers the MCP server and skill", () => {
  expect(claudeStep.id).toBe(`claude@${packageVersion()}`);
});

test("a state name with no matching cluster does not hide the real lab", () => {
  expect(pickUninstallTarget({ stateName: "crusty-bagel", clusters: ["toasty-scone"] })).toEqual({ target: "toasty-scone", guessed: true });
});

test("--cluster only accepts bakery-named clusters and never contradicts state", () => {
  expect(pickUninstallTarget({ explicit: "kind", clusters: ["kind"] }).error).toMatch(/not a gitops-bakery/);
  expect(pickUninstallTarget({ explicit: "golden-danish", stateName: "toasty-scone", clusters: ["golden-danish", "toasty-scone"] }).error).toMatch(
    /toasty-scone/,
  );
  expect(pickUninstallTarget({ explicit: "toasty-scone", clusters: ["toasty-scone"] })).toEqual({ target: "toasty-scone" });
});

test("deleteApp keeps the port and explains what to run when Argo CD never removes the Application", async () => {
  saveState({ ...loadState(), apps: { hello: { name: "hello", nodePort: 30010, createdAt: "" } } });
  const deps = {
    gitlab: { deleteFile: vi.fn(async () => {}), deleteProject: vi.fn(async () => {}) },
    argocd: { refresh: vi.fn(async () => {}), getApp: vi.fn(async () => ({ sync: "OutOfSync", health: "Healthy" })) },
    harbor: { deleteRepository: vi.fn(async () => {}) },
    kube: vi.fn(async () => ""),
    secrets: {},
    pollMs: 1,
    deleteTimeoutMs: 20,
  } as unknown as AppDeps;
  await expect(deleteApp(deps, "hello")).rejects.toThrow(/kubectl -n argocd delete application hello/);
  expect(loadState().apps.hello).toBeDefined();
  expect((deps.gitlab.deleteProject as ReturnType<typeof vi.fn>)).not.toHaveBeenCalled();
});

test("commitIfChanged skips identical content instead of guessing GitLab's error text", async () => {
  const gitlab = { readFile: vi.fn(async () => "same"), commitFiles: vi.fn(async () => "sha") };
  expect(await commitIfChanged(gitlab as never, "devops/service", { path: "root.yaml", content: "same" }, "m")).toBe(false);
  expect(gitlab.commitFiles).not.toHaveBeenCalled();
  gitlab.readFile.mockResolvedValueOnce("old");
  expect(await commitIfChanged(gitlab as never, "devops/service", { path: "root.yaml", content: "new" }, "m")).toBe(true);
});
