// Tests for the MCP tool set: names, input validation and secret hygiene
import { expect, test, vi } from "vitest";
import { buildTools } from "../../src/mcp/tools.js";
import type { AppDeps } from "../../src/apps/lifecycle.js";
import { loadState, saveState } from "../../src/lib/state.js";
import { useTempHome } from "../helpers/home.js";

useTempHome();

const secrets = {
  harborAdmin: "HARBORADMINSECRETVALUE01",
  grafanaAdmin: "GRAFANAADMINSECRETVAL02",
  valkey: "VALKEYSECRETVALUE0000003",
  webhook: "WEBHOOKSECRETVALUE000004",
  gitlabRootPassword: "GITLABROOTPASSWORD000005",
  gitlabPat: "glpat-PATSECRETVALUE0006",
  harborRobotSecret: "ROBOTSECRETVALUE00000007",
  argocdCiToken: "ARGOCI.TOKEN.SECRET.0008",
  argocdAdmin: "ARGOADMINSECRETVALUE0009",
};

function deps(): AppDeps {
  return {
    secrets,
    gitlab: {
      ensureProject: vi.fn(async (g: string, n: string) => ({ id: 1, pathWithNamespace: `${g}/${n}` })),
      commitFiles: vi.fn(async () => "sha"),
      createProjectToken: vi.fn(async () => "manifest-token-should-not-leak"),
      setVariable: vi.fn(async () => {}),
      deleteProject: vi.fn(async () => {}),
      deleteFile: vi.fn(async () => {}),
      latestPipeline: vi.fn(async () => ({ id: 1, status: "success", webUrl: "http://localhost/p/1", jobs: [] })),
    },
    harbor: { listTags: vi.fn(async () => ["abc"]), deleteRepository: vi.fn(async () => {}) },
    argocd: { getApp: vi.fn(async () => ({ sync: "Synced", health: "Healthy", revision: "r", reconciledAt: "" })) },
  } as unknown as AppDeps;
}

const status = async () => ({ cluster: "golden-danish", components: [{ namespace: "gitlab", ready: 9, total: 9 }] });

test("exactly the four bakery tools are offered", () => {
  expect(buildTools({ deps: async () => deps(), status }).map((t) => t.name).sort()).toEqual(
    ["bakery_app_status", "bakery_create_app", "bakery_delete_app", "bakery_status"],
  );
});

test("bakery_create_app rejects a bad name before touching anything", async () => {
  const d = deps();
  const tool = buildTools({ deps: async () => d, status }).find((t) => t.name === "bakery_create_app")!;
  expect(tool.inputSchema.safeParse({ name: "Bad!" }).success).toBe(false);
});

test("tool outputs never contain secret values", async () => {
  saveState({ ...loadState(), fastSync: "ci-refresh" });
  const d = deps();
  const tools = buildTools({ deps: async () => d, status });
  const run = (name: string, input: object) => tools.find((t) => t.name === name)!.handler(input as never);
  const outputs = [
    await run("bakery_status", {}),
    await run("bakery_create_app", { name: "hello" }),
    await run("bakery_app_status", { name: "hello" }),
    await run("bakery_delete_app", { name: "hello" }),
  ].map((o) => o.content.map((c) => c.text).join("\n"));
  for (const text of outputs) {
    for (const value of [...Object.values(secrets), "manifest-token-should-not-leak"]) expect(text).not.toContain(value);
  }
  expect(outputs[1]).toContain("http://localhost:30010");
});
