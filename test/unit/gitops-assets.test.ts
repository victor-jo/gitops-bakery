// Tests for the GitOps repo contents the installer commits to devops/platform and devops/service
import { expect, test } from "vitest";
import { parse } from "yaml";
import { gitopsFiles } from "../../src/steps/bootstrap.js";

const vars = { gitlabUrl: "http://gitlab.test:8181", grafanaAdmin: "pw" };
const platform = gitopsFiles("platform", vars);
const service = gitopsFiles("service", vars);
const file = (files: { path: string; content: string }[], p: string) => files.find((f) => f.path === p)!.content;

test("every rendered file parses and no placeholder is left", () => {
  for (const f of [...platform, ...service]) {
    if (f.path.endsWith(".json")) JSON.parse(f.content);
    else if (f.path.endsWith(".yaml")) parse(f.content);
    if (!f.path.endsWith(".json")) expect(f.content).not.toMatch(/\{\{\w+\}\}/);
  }
});

test("monitoring pins kube-prometheus-stack 92.10.1 with server-side apply", () => {
  const app = parse(file(platform, "apps/monitoring.yaml"));
  expect(app.spec.sources[0]).toMatchObject({ chart: "kube-prometheus-stack", targetRevision: "92.10.1" });
  expect(app.spec.syncPolicy.syncOptions).toContain("ServerSideApply=true");
});

test("monitoring values: no Alertmanager, any ServiceMonitor, Grafana on NodePort 30004 with the requests dashboard as home", () => {
  const v = parse(file(platform, "monitoring/values.yaml"));
  expect(v.alertmanager.enabled).toBe(false);
  expect(v.prometheus.prometheusSpec.serviceMonitorSelectorNilUsesHelmValues).toBe(false);
  expect(v.grafana.service).toMatchObject({ type: "NodePort", nodePort: 30004 });
  expect(v.grafana["grafana.ini"].dashboards.default_home_dashboard_path).toBe("/tmp/dashboards/requests.json");
  expect(v.grafana.admin.existingSecret).toBe("grafana-admin");
});

test("the dashboard shows a cumulative stat and per-minute increases for app namespaces", () => {
  const d = JSON.parse(file(platform, "monitoring/dashboards/requests.json"));
  const stat = d.panels.find((p: { type: string }) => p.type === "stat");
  expect(stat.fieldConfig.defaults.unit).toBe("none");
  const exprs = d.panels.flatMap((p: { targets: { expr: string }[] }) => p.targets.map((t) => t.expr)).join("\n");
  expect(exprs).toContain("increase(");
  expect(exprs).toContain('namespace=~"app-.*"');
});

test("root Applications live outside apps/ so they never manage themselves", () => {
  for (const files of [platform, service]) {
    expect(files.some((f) => f.path === "root.yaml")).toBe(true);
    expect(files.some((f) => f.path.startsWith("apps/") && f.path.endsWith("root.yaml"))).toBe(false);
  }
  expect(parse(file(service, "root.yaml")).spec.source.repoURL).toBe("http://gitlab.test:8181/devops/service.git");
});
