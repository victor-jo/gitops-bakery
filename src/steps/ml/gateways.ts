// Learns the gateway IP cloud-provider-kind gives each ML namespace and turns it into sslip.io host names
import { applyYaml, kubectl } from "../../lib/kube.js";
import { loadState, saveMlHosts, type MlHosts } from "../../lib/state.js";
import { waitFor } from "../../lib/wait.js";
import type { Step } from "../types.js";

// cloud-provider-kind runs one gateway per namespace, so names in the same namespace share an IP
export const GATEWAY_NAMESPACES: Record<string, (keyof MlHosts)[]> = {
  mlflow: ["mlflow", "jupyter"],
  feast: ["feast"],
  kubeflow: ["kfp"],
  monitoring: ["grafana"],
};

const PROBE = "bakery-gateway-probe";

export function sslipHost(name: string, ip: string): string {
  return `${name}.${ip.replace(/[.:]/g, "-")}.sslip.io`;
}

export function hostsFromIps(ips: Record<string, string>): MlHosts {
  const hosts = {} as MlHosts;
  for (const [ns, names] of Object.entries(GATEWAY_NAMESPACES)) for (const n of names) hosts[n] = sslipHost(n, ips[ns]);
  return hosts;
}

// The gateway only appears once an Ingress exists, and it stays after the last Ingress is gone, so a hostless probe is enough
function probeIngress(ns: string): string {
  return JSON.stringify({
    apiVersion: "networking.k8s.io/v1",
    kind: "Ingress",
    metadata: { name: PROBE, namespace: ns },
    spec: { ingressClassName: "cloud-provider-kind", defaultBackend: { service: { name: PROBE, port: { number: 80 } } } },
  });
}

export async function gatewayIp(ns: string): Promise<string> {
  const out = await kubectl(["-n", ns, "get", "gateway", "kind-ingress-gateway", "-o", "jsonpath={.status.addresses[*].value}"]);
  // The gateway also lists an IPv6 address; the IPv4 one is what macOS routes through lo0
  return out.split(/\s+/).find((a) => /^\d+\.\d+\.\d+\.\d+$/.test(a)) ?? "";
}

export async function deleteGatewayProbes(): Promise<void> {
  for (const ns of Object.keys(GATEWAY_NAMESPACES))
    await kubectl(["-n", ns, "delete", "ingress", PROBE, "--ignore-not-found"]);
}

export function mlHosts(): MlHosts {
  const hosts = loadState().ml?.hosts;
  if (!hosts) throw new Error("ML host names are not known yet; run install --with-ml again");
  return hosts;
}

export const mlGatewaysStep: Step = {
  id: "ml-gateways",
  title: "Gateway IPs and sslip.io names",
  async run() {
    const ips: Record<string, string> = {};
    for (const ns of Object.keys(GATEWAY_NAMESPACES)) {
      await kubectl(["create", "namespace", ns]).catch(() => undefined);
      if (!(await gatewayIp(ns).catch(() => ""))) await applyYaml(probeIngress(ns));
      await waitFor(`the ${ns} gateway IP from cloud-provider-kind (is 'sudo cloud-provider-kind' running?)`, async () => {
        ips[ns] = await gatewayIp(ns);
        return { ok: ips[ns] !== "", state: ips[ns] || "no address yet" };
      }, 3 * 60_000, 2000);
    }
    saveMlHosts(hostsFromIps(ips));
  },
};
