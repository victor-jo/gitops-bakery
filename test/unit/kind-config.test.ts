// Tests for the generated kind cluster config
import { expect, test } from "vitest";
import { parse } from "yaml";
import { kindConfig } from "../../src/kind/config.js";

const cfg = parse(kindConfig({ certsDir: "/tmp/certs.d", workers: 3 }));
const controlPlane = cfg.nodes[0];

test("containerd reads per-registry hosts.toml", () => {
  expect(cfg.containerdConfigPatches[0]).toContain('config_path = "/etc/containerd/certs.d"');
});

test("every node mounts the certs.d directory", () => {
  expect(cfg.nodes).toHaveLength(4);
  for (const node of cfg.nodes) {
    expect(node.extraMounts).toContainEqual({ hostPath: "/tmp/certs.d", containerPath: "/etc/containerd/certs.d" });
  }
});

test("control plane maps the lab ports on 127.0.0.1 only", () => {
  const hostPorts = controlPlane.extraPortMappings.map((m: { hostPort: number }) => m.hostPort);
  const appPorts = Array.from({ length: 10 }, (_, i) => 30010 + i);
  expect(hostPorts).toEqual([80, 30001, 30002, 30004, ...appPorts]);
  for (const m of controlPlane.extraPortMappings) expect(m.listenAddress).toBe("127.0.0.1");
});

test("host port 80 goes to the GitLab NodePort", () => {
  const gitlab = controlPlane.extraPortMappings.find((m: { hostPort: number }) => m.hostPort === 80);
  expect(gitlab.containerPort).toBe(30080);
});
