// Tests that an interrupted install can always be resumed or explains exactly what to run
import { existsSync, mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test } from "vitest";
import { garageChartReady, prepareGarageChart } from "../../src/steps/garage.js";
import { helmUpgrade } from "../../src/lib/helm.js";
import type { ExecResult } from "../../src/lib/exec.js";
import { useTempHome } from "../helpers/home.js";

useTempHome();

const CHART = join("script", "helm", "garage", "Chart.yaml");

test("a cache dir without Chart.yaml is not a usable Garage chart", () => {
  const dir = mkdtempSync(join(tmpdir(), "garage-"));
  expect(garageChartReady(dir)).toBe(false);
  mkdirSync(join(dir, "script", "helm", "garage"), { recursive: true });
  writeFileSync(join(dir, CHART), "name: garage\n");
  expect(garageChartReady(dir)).toBe(true);
});

test("a partial clone is thrown away and cloned again", async () => {
  const dir = join(mkdtempSync(join(tmpdir(), "garage-")), "cache");
  mkdirSync(dir);
  writeFileSync(join(dir, "half.txt"), "interrupted");
  const clones: string[] = [];
  await prepareGarageChart(dir, async (args) => {
    const target = args.at(-1)!;
    clones.push(target);
    mkdirSync(join(target, "script", "helm", "garage"), { recursive: true });
    writeFileSync(join(target, CHART), "name: garage\n");
  });
  expect(clones).toHaveLength(1);
  expect(clones[0]).not.toBe(dir);
  expect(garageChartReady(dir)).toBe(true);
  expect(existsSync(join(dir, "half.txt"))).toBe(false);
});

test("a ready cache is reused without cloning", async () => {
  const dir = mkdtempSync(join(tmpdir(), "garage-"));
  mkdirSync(join(dir, "script", "helm", "garage"), { recursive: true });
  writeFileSync(join(dir, CHART), "name: garage\n");
  let cloned = false;
  await prepareGarageChart(dir, async () => void (cloned = true));
  expect(cloned).toBe(false);
});

const ok = (stdout = ""): ExecResult => ({ code: 0, stdout, stderr: "" });

test("helmUpgrade stops with recovery commands when a release is stuck in pending-install", async () => {
  const calls: string[][] = [];
  const exec = async (_cmd: string, args: string[]) => {
    calls.push(args);
    if (args[0] === "status") return ok(JSON.stringify({ info: { status: "pending-install" } }));
    return ok();
  };
  await expect(helmUpgrade({ release: "gitlab", chart: "gitlab/gitlab", ns: "gitlab", values: "" }, exec)).rejects.toThrow(
    /gitlab.*pending-install[\s\S]*helm uninstall gitlab -n gitlab/,
  );
  expect(calls.some((a) => a[0] === "upgrade")).toBe(false);
});

test("helmUpgrade suggests a rollback for pending-upgrade and proceeds normally otherwise", async () => {
  const stuck = async (_c: string, args: string[]) =>
    args[0] === "status" ? ok(JSON.stringify({ info: { status: "pending-upgrade" } })) : ok();
  await expect(helmUpgrade({ release: "harbor", chart: "harbor/harbor", ns: "harbor", values: "" }, stuck)).rejects.toThrow(/helm rollback harbor -n harbor/);
  const calls: string[][] = [];
  const fresh = async (_c: string, args: string[]) => {
    calls.push(args);
    return args[0] === "status" ? { code: 1, stdout: "", stderr: "Error: release: not found" } : ok();
  };
  await helmUpgrade({ release: "harbor", chart: "harbor/harbor", ns: "harbor", values: "" }, fresh);
  expect(calls.some((a) => a[0] === "upgrade")).toBe(true);
});
