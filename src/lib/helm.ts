// helm upgrade --install wrapper pinned to the lab's kube context, values fed through stdin
import { run, type ExecOptions, type ExecResult } from "./exec.js";
import { kubeContext } from "./kube.js";

export type HelmRelease = {
  release: string;
  chart: string;
  version?: string;
  ns: string;
  repo?: { name: string; url: string };
  values: string;
  timeout?: string;
};

type Exec = (cmd: string, args: string[], opts?: ExecOptions) => Promise<ExecResult>;

// helm refuses to touch a release another (killed) helm left pending; name the exact way out instead of a cryptic retry loop
async function assertNotPending(o: HelmRelease, exec: Exec): Promise<void> {
  const res = await exec("helm", ["status", o.release, "-n", o.ns, "--kube-context", kubeContext(), "-o", "json"], { allowFail: true });
  if (res.code !== 0) return;
  const status = (JSON.parse(res.stdout) as { info?: { status?: string } }).info?.status ?? "";
  if (!status.startsWith("pending-")) return;
  const fix =
    status === "pending-install"
      ? `helm uninstall ${o.release} -n ${o.ns} --kube-context ${kubeContext()}`
      : `helm rollback ${o.release} -n ${o.ns} --kube-context ${kubeContext()}`;
  throw new Error(
    `Helm release ${o.release} is stuck in ${status} (an earlier install was interrupted).\nRun:\n  ${fix}\nthen run install again.`,
  );
}

export async function helmUpgrade(o: HelmRelease, exec: Exec = run): Promise<void> {
  await assertNotPending(o, exec);
  if (o.repo) {
    await exec("helm", ["repo", "add", o.repo.name, o.repo.url, "--force-update"]);
    await exec("helm", ["repo", "update", o.repo.name]);
  }
  const args = ["upgrade", "--install", o.release, o.chart, "-n", o.ns, "--create-namespace", "--wait",
    "--kube-context", kubeContext(), "--timeout", o.timeout ?? "10m", "-f", "-"];
  if (o.version) args.push("--version", o.version);
  await exec("helm", args, { input: o.values });
}
