// Tests for the cluster step's emulation probe image
import { expect, test } from "vitest";
import { AMD64_PROBE_IMAGE } from "../../src/steps/cluster.js";

test("amd64 probe pins a single-arch manifest by digest, like Harbor's images", () => {
  // A tag resolves to a multi-arch index, which arm64 containerd rejects with "no match for platform"
  expect(AMD64_PROBE_IMAGE).toMatch(/^alpine@sha256:[0-9a-f]{64}$/);
});

test("the emulation probe waits for the pod and reads its logs instead of attaching", async () => {
  const { checkAmd64Emulation } = await import("../../src/steps/cluster.js");
  const calls: string[][] = [];
  const kube = async (args: string[]) => {
    calls.push(args);
    return args[0] === "logs" ? "x86_64\n" : "";
  };
  await checkAmd64Emulation(kube);
  expect(calls.some((a) => a.includes("-i") || a.includes("--attach"))).toBe(false);
  expect(calls.map((a) => a[0])).toEqual(expect.arrayContaining(["run", "wait", "logs", "delete"]));
});

test("the emulation probe fails clearly on a non-amd64 answer", async () => {
  const { checkAmd64Emulation } = await import("../../src/steps/cluster.js");
  await expect(checkAmd64Emulation(async (a) => (a[0] === "logs" ? "aarch64\n" : ""))).rejects.toThrow(/Rosetta.*aarch64/s);
});
