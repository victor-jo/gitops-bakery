// Tests for the GitLab Runner values: in-cluster clone URL, host-arch helper and rootless BuildKit support
import { expect, test } from "vitest";
import { parse } from "yaml";
import { asset } from "../../src/lib/assets.js";

const values = parse(asset("values/gitlab-runner.yaml", { arch: "arm64" }));
const toml: string = values.runners.config;

test("jobs clone from the in-cluster GitLab address", () => {
  expect(values.gitlabUrl).toBe("http://gitlab-webservice-default.gitlab.svc.cluster.local:8181");
  expect(toml).toContain('clone_url = "http://gitlab-webservice-default.gitlab.svc.cluster.local:8181"');
});

test("job pods land on host-arch nodes so the helper image matches", () => {
  expect(toml).toContain('"kubernetes.io/arch" = "arm64"');
});

test("job pods run with an Unconfined seccomp profile for rootless BuildKit", () => {
  expect(toml).toContain('type = "Unconfined"');
});
