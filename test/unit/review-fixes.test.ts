// Regression tests for issues found in the final review
import { createServer } from "node:net";
import { expect, test, vi } from "vitest";
import { parse } from "yaml";
import { createApp, type AppDeps } from "../../src/apps/lifecycle.js";
import { loadState, saveState } from "../../src/lib/state.js";
import { gitopsFiles } from "../../src/steps/bootstrap.js";
import { ensureCiRobot } from "../../src/steps/harbor.js";
import { isPortFree, shouldCheckPorts } from "../../src/steps/preflight.js";
import { useTempHome } from "../helpers/home.js";

useTempHome();

test("a port held on 0.0.0.0 counts as busy", async () => {
  const server = createServer();
  await new Promise<void>((r) => server.listen(0, "0.0.0.0", () => r()));
  const port = (server.address() as { port: number }).port;
  try {
    expect(await isPortFree(port)).toBe(false);
  } finally {
    server.close();
  }
});

test("ports are not checked once the lab's own cluster exists (install --force, doctor on a live lab)", () => {
  expect(shouldCheckPorts(["kind", "airy-scone"], "airy-scone")).toBe(false);
  expect(shouldCheckPorts(["kind"], "airy-scone")).toBe(true);
});

test("the Grafana password never lands in the GitOps repo", () => {
  const files = gitopsFiles("platform", { gitlabUrl: "http://g", grafanaAdmin: "SUPERSECRETGRAFANA" } as never);
  for (const f of files) expect(f.content).not.toContain("SUPERSECRETGRAFANA");
  const values = parse(files.find((f) => f.path === "monitoring/values.yaml")!.content);
  expect(values.grafana.admin).toMatchObject({ existingSecret: "grafana-admin", userKey: "admin-user", passwordKey: "admin-password" });
  expect(values.grafana.adminPassword).toBeUndefined();
});

test("a working CI robot is kept, so existing apps keep pushing", async () => {
  const harbor = { robotWorks: vi.fn(async () => true), ensureRobot: vi.fn() };
  expect(await ensureCiRobot(harbor as never, "known-secret")).toBe("known-secret");
  expect(harbor.ensureRobot).not.toHaveBeenCalled();
});

function slowDeps() {
  const pause = () => new Promise((r) => setTimeout(r, 20));
  const gitlab = {
    createProject: vi.fn(async (g: string, n: string) => (await pause(), { id: 1, pathWithNamespace: `${g}/${n}` })),
    commitFiles: vi.fn(async () => (await pause(), "sha")),
    createProjectToken: vi.fn(async () => "tok"),
    setVariable: vi.fn(async () => {}),
    deleteProject: vi.fn(async () => {}),
    deleteFile: vi.fn(async () => {}),
  };
  const argocd = { refresh: vi.fn(async () => {}) };
  return { deps: { gitlab, harbor: { deleteRepository: vi.fn() }, argocd, secrets: { harborRobotSecret: "r", argocdCiToken: "c" } } as unknown as AppDeps, argocd };
}

test("apps created at the same time get different ports", async () => {
  saveState({ ...loadState(), fastSync: "ci-refresh" });
  const { deps } = slowDeps();
  const [a, b] = await Promise.all([createApp(deps, "a", "fastapi"), createApp(deps, "b", "fastapi")]);
  expect(a.url).not.toBe(b.url);
  expect(new Set(Object.values(loadState().apps).map((x) => x.nodePort)).size).toBe(2);
});

test("a failed Argo CD refresh does not roll the new app back", async () => {
  saveState({ ...loadState(), fastSync: "ci-refresh" });
  const { deps, argocd } = slowDeps();
  argocd.refresh.mockRejectedValue(new Error("argocd down"));
  await expect(createApp(deps, "hello", "fastapi")).resolves.toMatchObject({ url: "http://localhost:30010" });
  expect(loadState().apps.hello).toBeDefined();
});
