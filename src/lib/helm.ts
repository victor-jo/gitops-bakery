// helm upgrade --install wrapper pinned to the lab's kube context, values fed through stdin
import { run } from "./exec.js";
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

export async function helmUpgrade(o: HelmRelease): Promise<void> {
  if (o.repo) {
    await run("helm", ["repo", "add", o.repo.name, o.repo.url, "--force-update"]);
    await run("helm", ["repo", "update", o.repo.name]);
  }
  const args = ["upgrade", "--install", o.release, o.chart, "-n", o.ns, "--create-namespace", "--wait",
    "--kube-context", kubeContext(), "--timeout", o.timeout ?? "10m", "-f", "-"];
  if (o.version) args.push("--version", o.version);
  await run("helm", args, { input: o.values });
}
