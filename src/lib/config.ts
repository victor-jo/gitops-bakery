// Fixed lab constants: URLs, host ports and pinned component versions
export const GITLAB_INTERNAL_URL = "http://gitlab-webservice-default.gitlab.svc.cluster.local:8181";
export const GITLAB_HOST_URL = "http://localhost";
export const HARBOR_HOST_URL = "http://localhost:30001";
export const ARGOCD_HOST_URL = "http://localhost:30002";
export const GRAFANA_HOST_URL = "http://localhost:30004";

export const PORTS = {
  gitlab: 80,
  harbor: 30001,
  argocd: 30002,
  grafana: 30004,
  appMin: 30010,
  appMax: 30019,
} as const;

// GitLab's workhorse NodePort; host port 80 is mapped onto it
export const GITLAB_NODE_PORT = 30080;

export const VERSIONS = {
  kindNode: "kindest/node:v1.37.0",
  harborChart: "1.19.4",
  argocdChart: "10.10.5",
  gitlabChart: "10.5.0",
  gitlabRunnerChart: "0.94.0",
  cnpg: "1.30.1",
  valkeyChart: "0.12.0",
  garage: "v2.2.0",
  kubePrometheusStack: "92.10.1",
  buildkit: "moby/buildkit:v0.34.0-rootless",
} as const;
