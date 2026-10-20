// Tests for Garage bootstrap commands and the object-storage secrets GitLab reads
import { expect, test } from "vitest";
import { GITLAB_BUCKETS, garageCommands, objectStorageSecrets, parseGarageKey } from "../../src/steps/garage.js";

test("GitLab needs 14 buckets (the registry bucket is excluded)", () => {
  expect(GITLAB_BUCKETS).toHaveLength(14);
  expect(GITLAB_BUCKETS).not.toContain("registry");
  expect(GITLAB_BUCKETS).toContain("gitlab-artifacts");
});

test("garageCommands passes every argument as its own argv element", () => {
  const cmds = garageCommands("abc", ["a", "b"]);
  expect(cmds).toHaveLength(2 + 2 + 1 + 2);
  expect(cmds[0]).toEqual(["layout", "assign", "-z", "dc1", "-c", "1G", "abc"]);
  expect(cmds[1]).toEqual(["layout", "apply", "--version", "1"]);
  expect(cmds[2]).toEqual(["bucket", "create", "a"]);
  expect(cmds[4]).toEqual(["key", "create", "gitlab"]);
  expect(cmds[5]).toEqual(["bucket", "allow", "--read", "--write", "--owner", "a", "--key", "gitlab"]);
});

test("parseGarageKey reads the key id and secret from garage key output", () => {
  const out = "==== ACCESS KEY INFORMATION ====\nKey ID:              GK1234\nKey name:            gitlab\nSecret key:          abcd\n";
  expect(parseGarageKey(out)).toEqual({ id: "GK1234", secret: "abcd" });
});

test("objectStorageSecrets point at the in-cluster Garage over HTTP with path-style access", () => {
  const { connection, s3cmd } = objectStorageSecrets({ id: "GK1", secret: "S" });
  expect(connection).toContain("endpoint: http://garage.gitlab.svc.cluster.local:3900");
  expect(connection).toContain("path_style: true");
  expect(s3cmd).toContain("host_base = garage.gitlab.svc.cluster.local:3900");
  expect(s3cmd).toContain("use_https = False");
});

test("layoutVersion reads the applied layout version", async () => {
  const { layoutVersion } = await import("../../src/steps/garage.js");
  expect(layoutVersion("No nodes currently have a role\nCurrent cluster layout version: 0\n")).toBe(0);
  expect(layoutVersion("Current cluster layout version: 1")).toBe(1);
});

test("pendingGarageCommands drops work that is already done", async () => {
  const { pendingGarageCommands } = await import("../../src/steps/garage.js");
  const all = garageCommands("abc", ["a", "b"]);
  const pending = pendingGarageCommands(all, { layoutReady: true, buckets: new Set(["a"]), keyExists: true });
  expect(pending).toEqual([
    ["bucket", "create", "b"],
    ["bucket", "allow", "--read", "--write", "--owner", "a", "--key", "gitlab"],
    ["bucket", "allow", "--read", "--write", "--owner", "b", "--key", "gitlab"],
  ]);
});
