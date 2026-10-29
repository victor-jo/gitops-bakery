// Tests for the optional ML layer: step order, remembered flag, sslip.io names, rendered Applications, keys, secrets and seed Jobs
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "vitest";
import { parse, parseAllDocuments } from "yaml";
import { assetPath } from "../../src/lib/paths.js";
import { loadState, rememberOptions } from "../../src/lib/state.js";
import { ALL_STEPS, installSteps } from "../../src/steps/index.js";
import { hostsFromIps, sslipHost } from "../../src/steps/ml/gateways.js";
import { buildArgs } from "../../src/steps/ml/kfp-image.js";
import { ML_APPS, STALE_PLATFORM_FILES, changedFiles, mlPlatformFiles, syncedAt } from "../../src/steps/ml/platform.js";
import { SEED_JOBS, seedConfigMap, seedJob } from "../../src/steps/ml/seed.js";
import { ML_BUCKETS, ML_KEYS, grantCommands, mlSecrets } from "../../src/steps/ml/storage.js";
import { STALE_LB_HINT, minMemoryBytes, portProblems } from "../../src/steps/preflight.js";
import { useTempHome } from "../helpers/home.js";

useTempHome();

const hosts = hostsFromIps({ mlflow: "192.168.165.8", feast: "192.168.165.9", kubeflow: "192.168.165.7", monitoring: "192.168.165.10" });
const files = mlPlatformFiles(hosts);
const file = (p: string) => files.find((f) => f.path === p)!.content;

test("without --with-ml the install steps are unchanged; with it the ML steps follow the base lab in order", () => {
  expect(installSteps(false)).toBe(ALL_STEPS);
  const ids = installSteps(true).map((s) => s.id);
  expect(ids.slice(0, ALL_STEPS.length)).toEqual(ALL_STEPS.map((s) => s.id));
  expect(ids.slice(ALL_STEPS.length)).toEqual(["ml-preflight", "ml-storage", "ml-gateways", "ml-platform", "ml-seed", "ml-kfp-image"]);
});

test("--with-ml is remembered, so a later install without the flag still installs the ML layer", () => {
  expect(rememberOptions({}).ml).toBe(false);
  expect(rememberOptions({ ml: true }).ml).toBe(true);
  expect(rememberOptions({}).ml).toBe(true);
  expect(loadState().options).toEqual({ ml: true });
});

test("sslip.io names carry the gateway IP with dashes, and names in one namespace share its gateway", () => {
  expect(sslipHost("kfp", "192.168.165.7")).toBe("kfp.192-168-165-7.sslip.io");
  expect(hosts).toEqual({
    mlflow: "mlflow.192-168-165-8.sslip.io",
    jupyter: "jupyter.192-168-165-8.sslip.io",
    feast: "feast.192-168-165-9.sslip.io",
    kfp: "kfp.192-168-165-7.sslip.io",
    grafana: "grafana.192-168-165-10.sslip.io",
  });
});

test("every rendered ML file parses and no placeholder is left", () => {
  for (const f of files) {
    if (f.path.endsWith(".yaml")) for (const doc of parseAllDocuments(f.content)) expect(doc.errors).toEqual([]);
    if (!f.path.endsWith(".json")) expect(f.content).not.toMatch(/\{\{\w+\}\}/);
  }
});

test("each Ingress gets its sslip.io name and MLflow allows that name as Host and Origin", () => {
  const ingressHost = (p: string) => parse(file(p)).spec.rules[0].host;
  expect(ingressHost("mlflow/manifests/ingress.yaml")).toBe(hosts.mlflow);
  expect(ingressHost("jupyter/manifests/ingress.yaml")).toBe(hosts.jupyter);
  expect(ingressHost("feast/manifests/ingress.yaml")).toBe(hosts.feast);
  expect(ingressHost("kfp/manifests/30-ingress.yaml")).toBe(hosts.kfp);
  expect(parse(file("monitoring/values-ingress.yaml")).grafana.ingress.hosts).toEqual([hosts.grafana]);
  const env = parse(file("mlflow/values.yaml")).extraEnvVars;
  expect(env.MLFLOW_SERVER_ALLOWED_HOSTS.split(",")).toContain(hosts.mlflow);
  expect(env.MLFLOW_SERVER_CORS_ALLOWED_ORIGINS.split(",")).toContain(`http://${hosts.mlflow}`);
});

test("Grafana's ingress values are optional, so a lab without --with-ml syncs monitoring as before", () => {
  const helm = parse(file("apps/monitoring.yaml")).spec.sources[0].helm;
  expect(helm.ignoreMissingValueFiles).toBe(true);
  expect(helm.valueFiles).toEqual(["$values/monitoring/values.yaml", "$values/monitoring/values-ingress.yaml"]);
});

test("the ML apps pin MLflow chart 1.11.7, Feast 0.67.0 and KFP 2.18.0", () => {
  expect(parse(file("apps/mlflow.yaml")).spec.sources[0]).toMatchObject({ chart: "mlflow", targetRevision: "1.11.7" });
  expect(file("feast-operator/install.yaml")).toContain("quay.io/feastdev/feast-operator:0.67.0");
  expect(file("kfp/manifests/10-platform-agnostic.yaml")).toContain("ghcr.io/kubeflow/kfp-api-server:2.18.0");
  for (const app of ML_APPS.filter((a) => a !== "monitoring")) expect(files.some((f) => f.path === `apps/${app}.yaml`)).toBe(true);
});

test("no ML Service takes a NodePort, because 30010-30019 belong to bakery apps", () => {
  for (const f of files.filter((f) => f.path.endsWith(".yaml") && !f.path.startsWith("monitoring/"))) {
    for (const doc of parseAllDocuments(f.content)) {
      const o = doc.toJS();
      if (o?.kind === "Service") expect(o.spec.type ?? "ClusterIP", `${f.path} ${o.metadata.name}`).not.toBe("NodePort");
    }
  }
  for (const stale of STALE_PLATFORM_FILES) expect(files.some((f) => f.path === stale)).toBe(false);
});

test("Jupyter fetches the upstream notebook at a pinned commit and patches it instead of shipping a copy", () => {
  const deploy = file("jupyter/manifests/deployment.yaml");
  expect(deploy).toMatch(/chapter-4\/[0-9a-f]{40}/);
  expect(deploy).toContain("patch_notebook.py");
  const kustomization = parse(file("jupyter/manifests/kustomization.yaml"));
  expect(kustomization.configMapGenerator[0]).toEqual({ name: "jupyter-notebook", files: ["patch_notebook.py"] });
});

test("only files that differ from GitLab are committed", async () => {
  const sample = [{ path: "a.yaml", content: "same" }, { path: "b.yaml", content: "new" }, { path: "c.yaml", content: "x" }];
  const stored: Record<string, string | null> = { "a.yaml": "same", "b.yaml": "old", "c.yaml": null };
  const changed = await changedFiles({ readFile: async (_p, path) => stored[path] }, "devops/platform", sample);
  expect(changed.map((f) => f.path)).toEqual(["b.yaml", "c.yaml"]);
});

test("an app counts as done only once it is Synced and Healthy at the commit just pushed", () => {
  const ok = { sync: "Synced", health: "Healthy", reconciledAt: "" };
  expect(syncedAt({ ...ok, revision: "old" }, "new")).toBe(false);
  expect(syncedAt({ ...ok, revision: "new" }, "new")).toBe(true);
  expect(syncedAt({ ...ok, revision: "", revisions: ["chart-1.11.7", "new", "new"] }, "new")).toBe(true);
  expect(syncedAt({ ...ok, health: "Progressing", revision: "new" }, "new")).toBe(false);
  expect(syncedAt(null, "new")).toBe(false);
});

test("every ML bucket has an owner key, and kfp may read but not rewrite the feature buckets", () => {
  for (const b of ML_BUCKETS) expect(Object.values(ML_KEYS).some((k) => k.owner.includes(b)), b).toBe(true);
  const cmds = grantCommands().map((c) => c.join(" "));
  expect(cmds).toContain("bucket allow --read --write --owner inference-datasets --key kfp");
  expect(cmds).toContain("bucket allow --read feature-registry --key kfp");
  expect(cmds).not.toContain("bucket allow --read --write --owner feature-registry --key kfp");
});

test("the ML Secrets are the ones the manifests reference, and Feast uses Valkey db 1", () => {
  const key = (n: string) => ({ id: `GK${n}`, secret: `S${n}` });
  const keys = Object.fromEntries(Object.keys(ML_KEYS).map((n) => [n, key(n)]));
  const secrets = mlSecrets(keys, { valkey: "vk", jupyterToken: "jt" });
  expect(secrets.map((s) => `${s.metadata.namespace}/${s.metadata.name}`)).toEqual([
    "mlflow/mlflow-s3", "mlflow/jupyter-token", "feast/feast-s3", "feast/feast-online-store", "kubeflow/kfp-s3", "kubeflow/kfp-garage-artifact",
  ]);
  expect(secrets.find((s) => s.metadata.name === "feast-online-store")!.stringData.redis).toBe(
    "connection_string: valkey.gitlab.svc.cluster.local:6379,db=1,password=vk\n");
  // kfp-s3 is mounted by the pipeline itself, everything else by the committed manifests
  const pipeline = readFileSync(assetPath("labs", "ml", "kfp", "pipeline", "pipeline.py"), "utf8");
  const committed = files.map((f) => f.content).join("\n") + pipeline;
  for (const s of secrets) expect(committed).toContain(s.metadata.name);
});

test("seed Jobs run in the namespaces of the keys they use and carry no secret values themselves", () => {
  expect(SEED_JOBS.map((j) => `${j.ns}:${j.s3Secret}`)).toEqual(["feast:feast-s3", "kubeflow:kfp-s3"]);
  const job = seedJob(SEED_JOBS[0]) as { spec: { template: { spec: { containers: { command: string[]; env: object[] }[] } } } };
  const c = job.spec.template.spec.containers[0];
  expect(c.command.join(" ")).toContain("/seed/seed.py features");
  expect(JSON.stringify(c.env)).toContain('"secretKeyRef":{"name":"feast-online-store","key":"redis"}');
  const cm = seedConfigMap("feast") as { data: Record<string, string> };
  expect(Object.keys(cm.data).sort()).toEqual(["definitions.py", "seed.py"]);
});

test("the KFP image is built for the host architecture from the lab's own component code", () => {
  expect(buildArgs("arm64", "localhost:30001/kfp/income-pipeline:0.1.0", "/ctx")).toEqual(
    ["build", "--platform", "linux/arm64", "-t", "localhost:30001/kfp/income-pipeline:0.1.0", "/ctx"]);
  const context = assetPath("labs", "ml", "kfp", "pipeline", "src");
  expect(readdirSync(context).filter((n) => !n.startsWith(".") && n !== "__pycache__").sort())
    .toEqual(["Dockerfile", "components.py", "runtime-requirements.txt", "steps.py"]);
});

test("--with-ml raises the memory floor", () => {
  expect(minMemoryBytes(false)).toBe(10 * 1024 ** 3);
  expect(minMemoryBytes(true)).toBe(14 * 1024 ** 3);
});

test("the repo keeps no upstream example code, only the lab's patches and fetch scripts", () => {
  const walk = (d: string): string[] =>
    readdirSync(d).flatMap((n) => (statSync(join(d, n)).isDirectory() ? (n.startsWith(".venv") || n === "chapter-5" ? [] : walk(join(d, n))) : [join(d, n)]));
  const labFiles = walk(assetPath("labs", "ml"));
  for (const f of labFiles) expect(f, f).not.toMatch(/\/(src\/read_data|src\/run_inference|data_exploration_and_model_training\.ipynb)/);
  expect(readFileSync(assetPath("labs", "ml", "kfp", "upstream", "fetch.sh"), "utf8")).toMatch(/COMMIT=[0-9a-f]{40}/);
});

test("a busy port 80 next to a running cloud-provider-kind points at its stale LoadBalancer listeners", () => {
  expect(portProblems([80, 30001], true)).toEqual([STALE_LB_HINT, "Port 30001 on 127.0.0.1 is already in use; free it before installing"]);
  expect(portProblems([80], false)[0]).toContain("Port 80 on 127.0.0.1 is already in use");
});
