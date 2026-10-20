// Tests for the cluster step's emulation probe image
import { expect, test } from "vitest";
import { AMD64_PROBE_IMAGE } from "../../src/steps/cluster.js";

test("amd64 probe pins a single-arch manifest by digest, like Harbor's images", () => {
  // A tag resolves to a multi-arch index, which arm64 containerd rejects with "no match for platform"
  expect(AMD64_PROBE_IMAGE).toMatch(/^alpine@sha256:[0-9a-f]{64}$/);
});
