// Builds the kind cluster config: containerd registry patch, certs mounts and host port mappings
import { stringify } from "yaml";
import { GITLAB_NODE_PORT, PORTS } from "../lib/config.js";

const CERTS_IN_NODE = "/etc/containerd/certs.d";

function portMapping(hostPort: number, containerPort = hostPort) {
  return { containerPort, hostPort, listenAddress: "127.0.0.1" };
}

export function kindConfig(opts: { certsDir: string; workers: number }): string {
  const mounts = [{ hostPath: opts.certsDir, containerPath: CERTS_IN_NODE }];
  const appPorts = [];
  for (let p = PORTS.appMin; p <= PORTS.appMax; p++) appPorts.push(portMapping(p));
  const controlPlane = {
    role: "control-plane",
    extraMounts: mounts,
    extraPortMappings: [
      portMapping(PORTS.gitlab, GITLAB_NODE_PORT),
      portMapping(PORTS.harbor),
      portMapping(PORTS.argocd),
      portMapping(PORTS.grafana),
      ...appPorts,
    ],
  };
  const workers = Array.from({ length: opts.workers }, () => ({ role: "worker", extraMounts: mounts }));
  return stringify({
    kind: "Cluster",
    apiVersion: "kind.x-k8s.io/v1alpha4",
    containerdConfigPatches: [
      `[plugins."io.containerd.grpc.v1.cri".registry]\n  config_path = "${CERTS_IN_NODE}"`,
    ],
    nodes: [controlPlane, ...workers],
  });
}
