// Creates the kind cluster with Harbor trust baked in, then checks amd64 emulation for Harbor
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { VERSIONS } from "../lib/config.js";
import { run } from "../lib/exec.js";
import { kubectl } from "../lib/kube.js";
import { clusterName, registryHost } from "../lib/names.js";
import { assetPath, bakeryHome } from "../lib/paths.js";
import { render } from "../lib/template.js";
import { kindConfig } from "../kind/config.js";
import type { Step } from "./types.js";

export function certsDir(): string {
  return join(bakeryHome(), "certs.d");
}

function writeHostsToml(): void {
  const dir = join(certsDir(), registryHost());
  mkdirSync(dir, { recursive: true });
  const tmpl = readFileSync(assetPath("assets", "kind", "hosts.toml.tmpl"), "utf8");
  writeFileSync(join(dir, "hosts.toml"), render(tmpl, { registry: registryHost() }));
}

async function clusterExists(name: string): Promise<boolean> {
  const { stdout } = await run("kind", ["get", "clusters"]);
  return stdout.split("\n").includes(name);
}

// The linux/amd64 manifest of alpine:3.22, pinned by digest: Harbor ships single-arch amd64 manifests,
// and a plain manifest is pulled as-is while a multi-arch tag fails on arm64 nodes
export const AMD64_PROBE_IMAGE = "alpine@sha256:3e9b4b680bfc9fb5269227cffbd6d42be39fbf7c0b908123913864aa4447e764";

// Attaching with `kubectl run -i` races with a pod that exits in milliseconds and can return nothing,
// so the probe runs detached, waits for it to finish and reads its logs
export async function checkAmd64Emulation(kube: (args: string[]) => Promise<string> = kubectl): Promise<void> {
  const pod = "arch-check";
  await kube(["delete", "pod", pod, "--ignore-not-found", "--wait=true"]);
  await kube(["run", pod, "--restart=Never", `--image=${AMD64_PROBE_IMAGE}`, "--", "uname", "-m"]);
  await kube(["wait", `pod/${pod}`, "--for=jsonpath={.status.phase}=Succeeded", "--timeout=180s"]).catch(() => undefined);
  const out = await kube(["logs", pod]).catch((e: Error) => e.message);
  await kube(["delete", "pod", pod, "--ignore-not-found"]);
  if (!out.includes("x86_64"))
    throw new Error(`Harbor needs amd64 emulation (Rosetta); enable it in OrbStack/Docker Desktop settings. Got: ${out.trim()}`);
}

export const clusterStep: Step = {
  id: "cluster",
  title: "kind cluster",
  async run(ctx) {
    const name = clusterName();
    writeHostsToml();
    if (!(await clusterExists(name))) {
      ctx.log.info(`creating cluster ${name}`);
      await run("kind", ["create", "cluster", "--name", name, "--image", VERSIONS.kindNode, "--config", "-"], {
        input: kindConfig({ certsDir: certsDir(), workers: 3 }),
      });
    }
    await kubectl(["wait", "--for=condition=Ready", "nodes", "--all", "--timeout=180s"]);
    await checkAmd64Emulation();
  },
};
