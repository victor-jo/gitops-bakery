// Creates the ML lab's Garage buckets and keys and the Kubernetes Secrets that hand those keys to MLflow, Jupyter, Feast and KFP
import { kubectl, secretValue } from "../../lib/kube.js";
import { randomSecret, updateSecrets, type Secrets } from "../../lib/secrets.js";
import { garage, parseGarageKey } from "../garage.js";
import type { Step } from "../types.js";

export const ML_BUCKETS = ["mlflow", "mlflow-datasets", "feature-registry", "feature-data-sets", "inference-datasets", "mlpipeline"];

// Each key gets only the buckets its consumer touches; "read" keys can fetch features but not rewrite them
export const ML_KEYS: Record<string, { owner: string[]; read: string[] }> = {
  mlflow: { owner: ["mlflow", "mlflow-datasets"], read: [] },
  feast: { owner: ["feature-registry", "feature-data-sets"], read: [] },
  kfp: { owner: ["inference-datasets"], read: ["feature-registry", "feature-data-sets"] },
  "kfp-pipeline": { owner: ["mlpipeline"], read: [] },
};

export const ML_NAMESPACES = ["mlflow", "feast", "kubeflow"];

const VALKEY_HOST = "valkey.gitlab.svc.cluster.local:6379";

export function grantCommands(): string[][] {
  return Object.entries(ML_KEYS).flatMap(([key, g]) => [
    ...g.owner.map((b) => ["bucket", "allow", "--read", "--write", "--owner", b, "--key", key]),
    ...g.read.map((b) => ["bucket", "allow", "--read", b, "--key", key]),
  ]);
}

type Key = { id: string; secret: string };

function secret(ns: string, name: string, data: Record<string, string>) {
  return { apiVersion: "v1", kind: "Secret", metadata: { name, namespace: ns }, stringData: data };
}

// Valkey is shared with GitLab, which uses db 0, so Feast keeps its online rows in db 1
export function mlSecrets(keys: Record<string, Key>, s: Pick<Secrets, "valkey" | "jupyterToken">) {
  const aws = (k: Key) => ({ AWS_ACCESS_KEY_ID: k.id, AWS_SECRET_ACCESS_KEY: k.secret });
  return [
    secret("mlflow", "mlflow-s3", aws(keys.mlflow)),
    secret("mlflow", "jupyter-token", { token: s.jupyterToken! }),
    secret("feast", "feast-s3", aws(keys.feast)),
    secret("feast", "feast-online-store", { redis: `connection_string: ${VALKEY_HOST},db=1,password=${s.valkey}\n` }),
    secret("kubeflow", "kfp-s3", aws(keys.kfp)),
    secret("kubeflow", "kfp-garage-artifact", { accesskey: keys["kfp-pipeline"].id, secretkey: keys["kfp-pipeline"].secret }),
  ];
}

export const mlStorageStep: Step = {
  id: "ml-storage",
  title: "ML buckets, keys and secrets",
  async run(ctx) {
    const listing = await garage(["bucket", "list"]);
    for (const b of ML_BUCKETS) if (!new RegExp(`(^|\\s)${b}(\\s|$)`, "m").test(listing)) await garage(["bucket", "create", b]);
    const keys: Record<string, Key> = {};
    for (const name of Object.keys(ML_KEYS)) {
      if ((await garage(["key", "info", name], true)) === "") await garage(["key", "create", name]);
      keys[name] = parseGarageKey(await garage(["key", "info", name, "--show-secret"]));
    }
    for (const args of grantCommands()) await garage(args);

    for (const ns of ML_NAMESPACES) await kubectl(["create", "namespace", ns]).catch(() => undefined);
    // A lab whose Jupyter token was created by hand keeps it, so open browser sessions stay logged in
    const existing = await secretValue("mlflow", "jupyter-token", "token").catch(() => "");
    const secrets = ctx.secrets.jupyterToken ? ctx.secrets : updateSecrets({ jupyterToken: existing || randomSecret() });
    ctx.secrets.jupyterToken = secrets.jupyterToken;
    const values = Object.values(keys).map((k) => k.secret).concat(secrets.valkey, secrets.jupyterToken!);
    for (const s of mlSecrets(keys, secrets)) await kubectl(["apply", "-f", "-"], JSON.stringify(s), values);
  },
};
