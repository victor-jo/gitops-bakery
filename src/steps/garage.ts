// Installs Garage (S3) from its upstream chart, creates GitLab's buckets and key, and stores the object-storage secrets
import { existsSync, renameSync, rmSync } from "node:fs";
import { join } from "node:path";
import { VERSIONS } from "../lib/config.js";
import { asset } from "../lib/assets.js";
import { run } from "../lib/exec.js";
import { helmUpgrade } from "../lib/helm.js";
import { applyYaml, kubectl } from "../lib/kube.js";
import { bakeryHome } from "../lib/paths.js";
import type { Step } from "./types.js";

export const GITLAB_BUCKETS = [
  "git-lfs", "gitlab-agent-plan-content", "gitlab-artifacts", "gitlab-backups", "gitlab-ci-catalog-bundles",
  "gitlab-ci-secure-files", "gitlab-dependency-proxy", "gitlab-mr-diffs", "gitlab-packages", "gitlab-pages",
  "gitlab-terraform-state", "gitlab-uploads", "runner-cache", "tmp",
];

const KEY_NAME = "gitlab";
const ENDPOINT_HOST = "garage.gitlab.svc.cluster.local:3900";

export function garageChartReady(dir: string): boolean {
  return existsSync(join(dir, "script", "helm", "garage", "Chart.yaml"));
}

// Clone into a temp dir and rename, so an interrupted clone never leaves a half-filled cache that later runs trust
export async function prepareGarageChart(
  dir: string,
  clone: (args: string[]) => Promise<void> = async (args) => void (await run("git", args)),
): Promise<void> {
  if (garageChartReady(dir)) return;
  rmSync(dir, { recursive: true, force: true });
  const tmp = `${dir}.tmp-${process.pid}`;
  rmSync(tmp, { recursive: true, force: true });
  await clone(["clone", "--depth", "1", "--branch", VERSIONS.garage, "https://git.deuxfleurs.fr/Deuxfleurs/garage.git", tmp]);
  renameSync(tmp, dir);
}

// Each argument is its own array element, so no shell ever word-splits a bucket list
export function garageCommands(nodeId: string, buckets: string[]): string[][] {
  return [
    ["layout", "assign", "-z", "dc1", "-c", "1G", nodeId],
    ["layout", "apply", "--version", "1"],
    ...buckets.map((b) => ["bucket", "create", b]),
    ["key", "create", KEY_NAME],
    ...buckets.map((b) => ["bucket", "allow", "--read", "--write", "--owner", b, "--key", KEY_NAME]),
  ];
}

export function layoutVersion(layoutShow: string): number {
  return Number(/Current cluster layout version:\s*(\d+)/.exec(layoutShow)?.[1] ?? 0);
}

// Filters the full bootstrap list down to what has not happened yet, so reruns are safe
export function pendingGarageCommands(
  all: string[][],
  facts: { layoutReady: boolean; buckets: Set<string>; keyExists: boolean },
): string[][] {
  return all.filter((args) => {
    if (args[0] === "layout") return !facts.layoutReady;
    if (args[0] === "bucket" && args[1] === "create") return !facts.buckets.has(args[2]);
    if (args[0] === "key") return !facts.keyExists;
    return true;
  });
}

export function parseGarageKey(out: string): { id: string; secret: string } {
  const id = /Key ID:\s*(\S+)/.exec(out)?.[1];
  const secret = /Secret key:\s*(\S+)/.exec(out)?.[1];
  if (!id || !secret) throw new Error(`Could not read the Garage key from:\n${out}`);
  return { id, secret };
}

export function objectStorageSecrets(key: { id: string; secret: string }): { connection: string; s3cmd: string } {
  return {
    connection: [
      "provider: AWS",
      "region: garage",
      `aws_access_key_id: ${key.id}`,
      `aws_secret_access_key: ${key.secret}`,
      `endpoint: http://${ENDPOINT_HOST}`,
      "path_style: true",
      "",
    ].join("\n"),
    s3cmd: [
      "[default]",
      `access_key = ${key.id}`,
      `secret_key = ${key.secret}`,
      "bucket_location = garage",
      `host_base = ${ENDPOINT_HOST}`,
      `host_bucket = ${ENDPOINT_HOST}`,
      "use_https = False",
      "signature_v2 = False",
      "",
    ].join("\n"),
  };
}

async function garage(args: string[], allowFail = false): Promise<string> {
  try {
    return await kubectl(["-n", "gitlab", "exec", "garage-0", "-c", "garage", "--", "/garage", ...args]);
  } catch (e) {
    if (allowFail) return "";
    throw e;
  }
}

function secretYaml(name: string, data: string): string {
  return JSON.stringify({
    apiVersion: "v1",
    kind: "Secret",
    metadata: { name, namespace: "gitlab" },
    stringData: { config: data },
  });
}

export const garageStep: Step = {
  id: "garage",
  title: "Object storage (Garage)",
  async run() {
    const src = join(bakeryHome(), "cache", `garage-${VERSIONS.garage}`);
    await prepareGarageChart(src);
    await helmUpgrade({ release: "garage", chart: join(src, "script/helm/garage"), ns: "gitlab", values: asset("values/garage.yaml") });

    const nodeId = (await garage(["node", "id", "-q"])).trim().split("@")[0];
    const all = garageCommands(nodeId, GITLAB_BUCKETS);
    // Buckets cannot even be listed until a layout exists, so the layout goes first
    const layoutReady = layoutVersion(await garage(["layout", "show"])) > 0;
    for (const args of pendingGarageCommands(all.filter((a) => a[0] === "layout"), { layoutReady, buckets: new Set(), keyExists: false }))
      await garage(args);
    const listing = await garage(["bucket", "list"]);
    const buckets = new Set(GITLAB_BUCKETS.filter((b) => new RegExp(`(^|\\s)${b}(\\s|$)`, "m").test(listing)));
    const keyExists = (await garage(["key", "info", KEY_NAME], true)) !== "";
    for (const args of pendingGarageCommands(all.filter((a) => a[0] !== "layout"), { layoutReady: true, buckets, keyExists }))
      await garage(args);
    const key = parseGarageKey(await garage(["key", "info", KEY_NAME, "--show-secret"]));
    const { connection, s3cmd } = objectStorageSecrets(key);
    await applyYaml(secretYaml("gitlab-object-storage", connection));
    await applyYaml(secretYaml("gitlab-object-storage-s3cmd", s3cmd));
  },
};
