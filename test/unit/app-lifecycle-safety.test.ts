// Tests that app creation never adopts someone else's repo and that deletion fully releases the app
import { expect, test, vi } from "vitest";
import { parse } from "yaml";
import { createApp, deleteApp, type AppDeps } from "../../src/apps/lifecycle.js";
import { asset } from "../../src/lib/assets.js";
import { GitLab } from "../../src/lib/gitlab.js";
import { loadState, saveState } from "../../src/lib/state.js";
import { stubFetch } from "../helpers/fetch.js";
import { useTempHome } from "../helpers/home.js";

useTempHome();

function deps(over: Record<string, unknown> = {}) {
  const order: string[] = [];
  const gitlab = {
    createProject: vi.fn(async (g: string, n: string) => (order.push(`create ${g}/${n}`), { id: 1, pathWithNamespace: `${g}/${n}` })),
    commitFiles: vi.fn(async () => "sha"),
    createProjectToken: vi.fn(async () => "tok"),
    setVariable: vi.fn(async () => {}),
    deleteProject: vi.fn(async (p: string) => void order.push(`deleteProject ${p}`)),
    deleteFile: vi.fn(async () => void order.push("deleteFile")),
    ...((over.gitlab as object) ?? {}),
  };
  let appGone = 0;
  const argocd = {
    refresh: vi.fn(async () => void order.push("refresh")),
    getApp: vi.fn(async () => (appGone++ < 1 ? { sync: "Synced", health: "Healthy" } : null)),
  };
  const kube = vi.fn(async (args: string[]) => (order.push(`kube ${args.join(" ")}`), ""));
  const harbor = { deleteRepository: vi.fn(async () => void order.push("harbor")) };
  const d = { gitlab, argocd, kube, harbor, secrets: { harborRobotSecret: "r", argocdCiToken: "c" }, pollMs: 1 } as unknown as AppDeps;
  return { d, gitlab, order };
}

test("createProject refuses a path that already holds a live project", async () => {
  const { fn } = stubFetch({
    "GET /api/v4/projects/apps%2Ftaken": { status: 200, body: { id: 4, path_with_namespace: "apps/taken", marked_for_deletion_on: null } },
  });
  await expect(new GitLab("http://g", "t", fn).createProject("apps", "taken")).rejects.toThrow(/already exists/);
});

test("createApp refuses an existing GitLab project and deletes nothing", async () => {
  saveState({ ...loadState(), fastSync: "ci-refresh" });
  const { d, gitlab } = deps({
    gitlab: { createProject: vi.fn(async () => { throw new Error("GitLab project apps/taken-manifests already exists; delete it or pick another name"); }) },
  });
  await expect(createApp(d, "taken", "fastapi")).rejects.toThrow(/already exists/);
  expect(gitlab.deleteProject).not.toHaveBeenCalled();
  expect(loadState().apps.taken).toBeUndefined();
});

test("rollback removes only the projects this call created", async () => {
  saveState({ ...loadState(), fastSync: "ci-refresh" });
  const { d, gitlab } = deps();
  gitlab.createProject
    .mockImplementationOnce(async () => ({ id: 1, pathWithNamespace: "apps/x-manifests" }))
    .mockImplementationOnce(async () => { throw new Error("GitLab project apps/x already exists; delete it or pick another name"); });
  await expect(createApp(d, "x", "fastapi")).rejects.toThrow(/already exists/);
  expect(gitlab.deleteProject.mock.calls.map((c) => c[0])).toEqual(["apps/x-manifests"]);
});

test("deleteApp releases the port only after the Application and namespace are gone", async () => {
  saveState({ ...loadState(), apps: { hello: { name: "hello", nodePort: 30010, createdAt: "" } } });
  const { d, order } = deps();
  await deleteApp(d, "hello");
  const nsDelete = order.findIndex((o) => o.startsWith("kube delete namespace app-hello"));
  expect(order.indexOf("deleteFile")).toBeLessThan(order.indexOf("refresh"));
  expect(nsDelete).toBeGreaterThan(order.indexOf("refresh"));
  expect(loadState().apps.hello).toBeUndefined();
});

test("app Applications cascade-delete their resources", () => {
  const app = parse(asset("gitops/app-application.yaml.tmpl", { name: "hello", gitlabUrl: "http://g" }));
  expect(app.metadata.finalizers).toContain("resources-finalizer.argocd.argoproj.io");
});
