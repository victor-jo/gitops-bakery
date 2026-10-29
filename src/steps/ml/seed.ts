// Runs the ML seed Jobs inside the cluster, so the Mac needs no Python: datasets into Garage, Feast registries and online rows
import { readFileSync } from "node:fs";
import { applyYaml, kubectl } from "../../lib/kube.js";
import { assetPath } from "../../lib/paths.js";
import { waitFor } from "../../lib/wait.js";
import type { Step } from "../types.js";

export const FEAST_IMAGE = "quay.io/feastdev/feature-server:0.67.0";

// Each Job runs where its key's Secret lives: Feast data under the feast key, the scoring input under the kfp key
export const SEED_JOBS = [
  { mode: "features", ns: "feast", s3Secret: "feast-s3" },
  { mode: "inference", ns: "kubeflow", s3Secret: "kfp-s3" },
] as const;

type SeedJob = (typeof SEED_JOBS)[number];

export function seedConfigMap(ns: string): object {
  const file = (name: string) => readFileSync(assetPath("assets", "ml", "seed", name), "utf8");
  return {
    apiVersion: "v1",
    kind: "ConfigMap",
    metadata: { name: "ml-seed", namespace: ns },
    data: { "seed.py": file("seed.py"), "definitions.py": file("definitions.py") },
  };
}

export function seedJob(job: SeedJob): object {
  const env = [
    { name: "AWS_DEFAULT_REGION", value: "garage" },
    { name: "FEAST_S3_ENDPOINT_URL", value: "http://garage.gitlab.svc.cluster.local:3900" },
    { name: "AWS_ENDPOINT_URL", value: "http://garage.gitlab.svc.cluster.local:3900" },
    ...(job.mode === "features"
      ? [{ name: "FEAST_ONLINE_STORE", valueFrom: { secretKeyRef: { name: "feast-online-store", key: "redis" } } }]
      : []),
  ];
  return {
    apiVersion: "batch/v1",
    kind: "Job",
    metadata: { name: `ml-seed-${job.mode}`, namespace: job.ns },
    spec: {
      backoffLimit: 2,
      ttlSecondsAfterFinished: 86400,
      template: {
        spec: {
          restartPolicy: "Never",
          containers: [{
            name: "seed",
            image: FEAST_IMAGE,
            // The feature server image reads S3 registries but lacks s3fs, which the file offline store needs to materialize
            command: ["sh", "-c", `pip install -q s3fs && python /seed/seed.py ${job.mode}`],
            env,
            envFrom: [{ secretRef: { name: job.s3Secret } }],
            volumeMounts: [{ name: "seed", mountPath: "/seed" }],
          }],
          volumes: [{ name: "seed", configMap: { name: "ml-seed" } }],
        },
      },
    },
  };
}

async function jobState(ns: string, name: string): Promise<"done" | "failed" | "running"> {
  const out = await kubectl(["-n", ns, "get", "job", name, "-o", "jsonpath={.status.succeeded}/{.status.failed}"]);
  const [ok, failed] = out.split("/").map((n) => Number(n || 0));
  if (ok > 0) return "done";
  return failed > 2 ? "failed" : "running";
}

export const mlSeedStep: Step = {
  id: "ml-seed",
  title: "ML seed data (Garage datasets, Feast registries, online store)",
  async run(ctx) {
    for (const job of SEED_JOBS) {
      const name = `ml-seed-${job.mode}`;
      await applyYaml(JSON.stringify(seedConfigMap(job.ns)));
      // A Job's pod template is immutable, so a rerun replaces the old Job instead of patching it
      await kubectl(["-n", job.ns, "delete", "job", name, "--ignore-not-found"]);
      await applyYaml(JSON.stringify(seedJob(job)));
      let state = "running";
      await waitFor(`Job ${job.ns}/${name}`, async () => {
        state = await jobState(job.ns, name);
        return { ok: state !== "running", state };
      }, 20 * 60_000);
      // Feast errors can echo the online store connection string, so the Valkey password is masked before printing
      const raw = await kubectl(["-n", job.ns, "logs", `job/${name}`, "--tail", "20"]).catch(() => "");
      const logs = raw.split(ctx.secrets.valkey).join("***");
      if (state === "failed") throw new Error(`Job ${job.ns}/${name} failed:\n${logs}`);
      for (const line of logs.split("\n").filter((l) => l.startsWith("online store keys"))) ctx.log.info(line);
    }
  },
};
