// Tests for the GitLab API client used by bootstrap and the app lifecycle
import { expect, test } from "vitest";
import { GitLab } from "../../src/lib/gitlab.js";
import { stubFetch } from "../helpers/fetch.js";

const base = "http://localhost";
const proj = "/api/v4/projects/apps%2Fhello";

test("setVariable creates the variable raw so GitLab never expands $ in it", async () => {
  const { fn, calls } = stubFetch({ [`POST ${proj}/variables`]: { status: 201 } });
  await new GitLab(base, "t", fn).setVariable("apps/hello", "HARBOR_USER", "robot$apps+ci", { raw: true, masked: false });
  expect(calls[0].body).toMatchObject({ key: "HARBOR_USER", value: "robot$apps+ci", raw: true, masked: false });
});

test("setVariable updates an existing variable", async () => {
  const { fn, calls } = stubFetch({
    [`POST ${proj}/variables`]: { status: 400, body: { message: { key: ["(HARBOR_USER) has already been taken"] } } },
    [`PUT ${proj}/variables/HARBOR_USER`]: { status: 200 },
  });
  await new GitLab(base, "t", fn).setVariable("apps/hello", "HARBOR_USER", "v", { raw: true, masked: false });
  expect(calls.map((c) => c.method)).toEqual(["POST", "PUT"]);
});

test("commitFiles updates files that exist and creates the rest", async () => {
  const { fn, calls } = stubFetch({
    [`GET ${proj}/repository/files/a.txt?ref=main`]: { status: 200, body: {} },
    [`GET ${proj}/repository/files/dir%2Fb.txt?ref=main`]: { status: 404 },
    [`POST ${proj}/repository/commits`]: { status: 201, body: { id: "sha1" } },
  });
  const sha = await new GitLab(base, "t", fn).commitFiles(
    "apps/hello",
    [{ path: "a.txt", content: "1" }, { path: "dir/b.txt", content: "2" }],
    "msg",
  );
  expect(sha).toBe("sha1");
  const commit = calls.at(-1)!.body as { actions: { action: string; file_path: string }[] };
  expect(commit.actions.map((a) => [a.action, a.file_path])).toEqual([["update", "a.txt"], ["create", "dir/b.txt"]]);
});

test("ensureGroup does not create a group that exists", async () => {
  const { fn, calls } = stubFetch({ "GET /api/v4/groups/devops": { status: 200, body: { id: 5 } } });
  expect(await new GitLab(base, "t", fn).ensureGroup("devops")).toBe(5);
  expect(calls.filter((c) => c.method === "POST")).toHaveLength(0);
});

test("ensureProject creates a public project inside the group", async () => {
  const { fn, calls } = stubFetch({
    "GET /api/v4/projects/devops%2Fplatform": { status: 404 },
    "GET /api/v4/groups/devops": { status: 200, body: { id: 5 } },
    "POST /api/v4/projects": { status: 201, body: { id: 9, path_with_namespace: "devops/platform" } },
  });
  const p = await new GitLab(base, "t", fn).ensureProject("devops", "platform");
  expect(p).toEqual({ id: 9, pathWithNamespace: "devops/platform" });
  expect(calls.at(-1)!.body).toMatchObject({ path: "platform", namespace_id: 5, visibility: "public" });
});

test("deleteProject marks by id, then permanently removes using the renamed path", async () => {
  const { fn, calls } = stubFetch({
    "GET /api/v4/projects/apps%2Fhello": { status: 200, body: { id: 7, path_with_namespace: "apps/hello", marked_for_deletion_on: null } },
    "DELETE /api/v4/projects/7": { status: 202 },
    "GET /api/v4/projects/7": { status: 200, body: { id: 7, path_with_namespace: "apps/hello-deletion_scheduled-7" } },
    "DELETE /api/v4/projects/7?permanently_remove=true&full_path=apps%2Fhello-deletion_scheduled-7": { status: 202 },
  });
  await new GitLab(base, "t", fn).deleteProject("apps/hello");
  expect(calls.map((c) => `${c.method} ${c.path}`)).toEqual([
    "GET /api/v4/projects/apps%2Fhello",
    "DELETE /api/v4/projects/7",
    "GET /api/v4/projects/7",
    "DELETE /api/v4/projects/7?permanently_remove=true&full_path=apps%2Fhello-deletion_scheduled-7",
  ]);
});

test("ensureProject ignores a project that is only scheduled for deletion and creates a fresh one", async () => {
  const { fn, calls } = stubFetch({
    "GET /api/v4/projects/apps%2Fhello": {
      status: 200,
      body: { id: 7, path_with_namespace: "apps/hello-deletion_scheduled-7", marked_for_deletion_on: "2026-10-27" },
    },
    "GET /api/v4/groups/apps": { status: 200, body: { id: 3 } },
    "POST /api/v4/projects": { status: 201, body: { id: 8, path_with_namespace: "apps/hello" } },
  });
  expect(await new GitLab(base, "t", fn).ensureProject("apps", "hello")).toEqual({ id: 8, pathWithNamespace: "apps/hello" });
  expect(calls.some((c) => c.method === "POST")).toBe(true);
});
