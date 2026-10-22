// Tests for app names, port allocation, the FastAPI template and createApp's guard rails
import { expect, test, vi } from "vitest";
import type { AppRecord } from "../../src/lib/state.js";
import { loadState, saveState } from "../../src/lib/state.js";
import { validateAppName } from "../../src/apps/names.js";
import { allocatePort } from "../../src/apps/ports.js";
import { createApp, templateFiles, type AppDeps } from "../../src/apps/lifecycle.js";
import { useTempHome } from "../helpers/home.js";

useTempHome();

const rec = (nodePort: number) => ({ nodePort }) as AppRecord;

test("app names must be DNS labels of at most 30 characters", () => {
  expect(() => validateAppName("Hello")).toThrow(/Invalid app name/);
  expect(() => validateAppName("a".repeat(31))).toThrow(/Invalid app name/);
  expect(() => validateAppName("-x")).toThrow(/Invalid app name/);
  expect(() => validateAppName("hello-api")).not.toThrow();
});

test("app names may not collide with the lab's own Applications", () => {
  for (const n of ["monitoring", "platform-root", "service-root"]) expect(() => validateAppName(n)).toThrow(/reserved/);
});

test("allocatePort hands out the lowest free port in 30010-30019", () => {
  expect(allocatePort({})).toBe(30010);
  expect(allocatePort({ a: rec(30010) })).toBe(30011);
  expect(allocatePort({ a: rec(30011) })).toBe(30010);
});

test("allocatePort refuses an 11th app", () => {
  const apps = Object.fromEntries(Array.from({ length: 10 }, (_, i) => [`a${i}`, rec(30010 + i)]));
  expect(() => allocatePort(apps)).toThrow(/No free app port/);
});

test("every template file renders with no placeholder left", () => {
  const vars = { name: "hello", registry: "r:30001", nodePort: 30010, image: "r:30001/apps/hello" };
  for (const kind of ["app", "manifests"] as const) {
    const files = templateFiles(kind, vars);
    expect(files.length).toBeGreaterThan(0);
    for (const f of files) expect(f.content).not.toMatch(/\{\{\w+\}\}/);
  }
});

test("the CI template keeps the quoted sed line and refreshes Argo CD only when given a token", () => {
  const ci = templateFiles("app", { name: "hello", registry: "r:30001", nodePort: 30010, image: "r:30001/apps/hello" })
    .find((f) => f.path === ".gitlab-ci.yml")!.content;
  expect(ci).toContain(`- 'sed -i "s/newTag: .*/newTag: $CI_COMMIT_SHORT_SHA/" kustomization.yaml'`);
  expect(ci).toContain("git pull --rebase");
  expect(ci).toContain("/api/v1/applications/hello?refresh=normal");
  expect(ci).toContain('if [ -n "$ARGOCD_TOKEN" ]');
  // The refresh only speeds things up; Argo CD still polls, so it must never fail the deploy job
  expect(ci).toMatch(/refresh=normal" \|\| echo /);
});

function fakeDeps() {
  const gitlab = {
    createProject: vi.fn(async (g: string, n: string) => ({ id: 1, pathWithNamespace: `${g}/${n}` })),
    commitFiles: vi.fn(async () => "sha"),
    createProjectToken: vi.fn(async () => "tok"),
    setVariable: vi.fn(async () => {}),
    deleteProject: vi.fn(async () => {}),
    deleteFile: vi.fn(async () => {}),
  };
  const harbor = { deleteRepository: vi.fn(async () => {}) };
  const argocd = { refresh: vi.fn(async () => {}) };
  const deps = { gitlab, harbor, argocd, secrets: { harborRobotSecret: "robot-secret", argocdCiToken: "ci-token" } } as unknown as AppDeps;
  return { deps, gitlab, harbor, argocd };
}

test("createApp rejects a duplicate before touching GitLab", async () => {
  saveState({ ...loadState(), fastSync: "ci-refresh", apps: { hello: { name: "hello", nodePort: 30010, createdAt: "" } } });
  const { deps, gitlab } = fakeDeps();
  await expect(createApp(deps, "hello", "fastapi")).rejects.toThrow(/already exists/);
  expect(gitlab.createProject).not.toHaveBeenCalled();
});

test("createApp sets raw CI variables and records the app", async () => {
  saveState({ ...loadState(), fastSync: "ci-refresh" });
  const { deps, gitlab } = fakeDeps();
  const out = await createApp(deps, "hello", "fastapi");
  expect(out.url).toBe("http://localhost:30010");
  const keys = gitlab.setVariable.mock.calls.map((c) => [c[1], c[3]]);
  expect(keys).toEqual([
    ["HARBOR_USER", { raw: true, masked: false }],
    ["HARBOR_PASSWORD", { raw: true, masked: true }],
    ["MANIFEST_TOKEN", { raw: true, masked: true }],
    ["ARGOCD_TOKEN", { raw: true, masked: true }],
  ]);
  expect(gitlab.setVariable.mock.calls[0][2]).toBe("robot$apps+ci");
  expect(loadState().apps.hello.nodePort).toBe(30010);
});

test("createApp asks Argo CD to pick up the new Application right away", async () => {
  saveState({ ...loadState(), fastSync: "ci-refresh" });
  const { deps, argocd } = fakeDeps();
  await createApp(deps, "hello", "fastapi");
  expect(argocd.refresh).toHaveBeenCalledWith("service-root");
});

test("createApp rolls back both repos when a later step fails", async () => {
  saveState({ ...loadState(), fastSync: "ci-refresh" });
  const { deps, gitlab } = fakeDeps();
  gitlab.commitFiles.mockImplementation(async (project: string) => {
    if (project === "apps/hello") throw new Error("push failed");
    return "sha";
  });
  await expect(createApp(deps, "hello", "fastapi")).rejects.toThrow("push failed");
  expect(gitlab.deleteProject.mock.calls.map((c) => c[0]).sort()).toEqual(["apps/hello", "apps/hello-manifests"]);
  expect(loadState().apps.hello).toBeUndefined();
});
