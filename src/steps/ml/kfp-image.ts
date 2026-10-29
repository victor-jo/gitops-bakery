// Builds the KFP component image for the host architecture and pushes it to Harbor's public "kfp" project
import { existsSync, mkdtempSync, rmSync, symlinkSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { join } from "node:path";
import { HARBOR_HOST_URL } from "../../lib/config.js";
import { run } from "../../lib/exec.js";
import { Harbor } from "../../lib/harbor.js";
import { registryHost } from "../../lib/names.js";
import { assetPath } from "../../lib/paths.js";
import { waitFor } from "../../lib/wait.js";
import type { Step } from "../types.js";

export const KFP_PROJECT = "kfp";
export const KFP_IMAGE = "income-pipeline:0.1.0";

// The Mac pushes through Harbor's host port, while pods pull the same repository by the node's name
export function kfpImageRefs(): { push: string; pull: string } {
  return { push: `localhost:30001/${KFP_PROJECT}/${KFP_IMAGE}`, pull: `${registryHost()}/${KFP_PROJECT}/${KFP_IMAGE}` };
}

// `kfp component build` always targets amd64, so the image is built straight from the Dockerfile it generated
export function buildArgs(arch: string, tag: string, context: string): string[] {
  return ["build", "--platform", `linux/${arch}`, "-t", tag, context];
}

// A throwaway Docker config keeps the Harbor login out of the user's own ~/.docker, while reusing their CLI plugins and daemon
async function isolatedDockerEnv(): Promise<{ env: Record<string, string>; cleanup(): void }> {
  const dir = mkdtempSync(join(tmpdir(), "bakery-docker-"));
  const plugins = join(homedir(), ".docker", "cli-plugins");
  if (existsSync(plugins)) symlinkSync(plugins, join(dir, "cli-plugins"));
  const host = (await run("docker", ["context", "inspect", "--format", "{{.Endpoints.docker.Host}}"])).stdout.trim();
  return { env: { DOCKER_CONFIG: dir, DOCKER_HOST: host }, cleanup: () => rmSync(dir, { recursive: true, force: true }) };
}

export const mlKfpImageStep: Step = {
  id: "ml-kfp-image",
  title: "KFP component image in Harbor",
  async run(ctx) {
    // Harbor's amd64 database restarts now and then under emulation when its 1 s probe times out, so wait for it first
    await waitFor("Harbor API", async () => {
      const r = await fetch(`${HARBOR_HOST_URL}/api/v2.0/health`);
      return { ok: r.ok, state: `HTTP ${r.status}` };
    }, 10 * 60_000);
    await new Harbor(HARBOR_HOST_URL, "admin", ctx.secrets.harborAdmin).ensureProject(KFP_PROJECT, true);
    const { push } = kfpImageRefs();
    const docker = await isolatedDockerEnv();
    try {
      await run("docker", ["login", "localhost:30001", "-u", "admin", "--password-stdin"], {
        env: docker.env,
        input: ctx.secrets.harborAdmin,
        redact: [ctx.secrets.harborAdmin],
      });
      await run("docker", buildArgs(ctx.arch, push, assetPath("labs", "ml", "kfp", "pipeline", "src")), { env: docker.env });
      await run("docker", ["push", push], { env: docker.env });
    } finally {
      docker.cleanup();
    }
  },
};
