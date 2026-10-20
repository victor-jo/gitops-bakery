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

async function checkAmd64Emulation(): Promise<void> {
  const out = await kubectl(["run", "arch-check", "--rm", "-i", "--restart=Never", "--quiet",
    "--image=amd64/alpine:3.22", "--", "uname", "-m"]).catch((e: Error) => e.message);
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
    await checkAmd64Emulation();
  },
};
