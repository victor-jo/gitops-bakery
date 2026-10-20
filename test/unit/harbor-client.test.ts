// Tests for the Harbor API client used by install and the app lifecycle
import { expect, test } from "vitest";
import { Harbor } from "../../src/lib/harbor.js";
import { stubFetch } from "../helpers/fetch.js";

const base = "http://localhost:30001";

test("ensureProject creates a public project when it is missing", async () => {
  const { fn, calls } = stubFetch({
    "HEAD /api/v2.0/projects?project_name=apps": { status: 404 },
    "POST /api/v2.0/projects": { status: 201 },
  });
  await new Harbor(base, "admin", "pw", fn).ensureProject("apps", true);
  expect(calls.at(-1)).toEqual({ method: "POST", path: "/api/v2.0/projects", body: { project_name: "apps", metadata: { public: "true" } } });
});

test("ensureProject does nothing when the project exists", async () => {
  const { fn, calls } = stubFetch({ "HEAD /api/v2.0/projects?project_name=apps": { status: 200 } });
  await new Harbor(base, "admin", "pw", fn).ensureProject("apps", true);
  expect(calls.filter((c) => c.method === "POST")).toHaveLength(0);
});

test("ensureRobot creates a push/pull robot and returns its full name and secret", async () => {
  const { fn, calls } = stubFetch({
    "GET /api/v2.0/robots*": { status: 200, body: [] },
    "POST /api/v2.0/robots": { status: 201, body: { name: "robot$apps+ci", secret: "s3cret" } },
  });
  const robot = await new Harbor(base, "admin", "pw", fn).ensureRobot("apps", "ci");
  expect(robot).toEqual({ name: "robot$apps+ci", secret: "s3cret" });
  const post = calls.find((c) => c.method === "POST")!.body as { permissions: { access: { resource: string; action: string }[] }[] };
  expect(post.permissions[0].access).toEqual(
    expect.arrayContaining([{ resource: "repository", action: "push" }, { resource: "repository", action: "pull" }]),
  );
});

test("ensureRobot replaces an existing robot because its secret cannot be read back", async () => {
  const { fn, calls } = stubFetch({
    "GET /api/v2.0/robots*": { status: 200, body: [{ id: 7, name: "robot$apps+ci" }] },
    "DELETE /api/v2.0/robots/7": { status: 200 },
    "POST /api/v2.0/robots": { status: 201, body: { name: "robot$apps+ci", secret: "new" } },
  });
  await new Harbor(base, "admin", "pw", fn).ensureRobot("apps", "ci");
  expect(calls.map((c) => c.method)).toEqual(["GET", "DELETE", "POST"]);
});

test("listTags flattens artifact tags", async () => {
  const { fn } = stubFetch({
    "GET /api/v2.0/projects/apps/repositories/hello/artifacts*": { status: 200, body: [{ tags: [{ name: "abc" }, { name: "latest" }] }, { tags: null }] },
  });
  expect(await new Harbor(base, "admin", "pw", fn).listTags("apps", "hello")).toEqual(["abc", "latest"]);
});
