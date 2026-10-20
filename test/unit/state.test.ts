// Tests for the install state file and the random cluster name
import { expect, test } from "vitest";
import { isDone, loadState, markDone } from "../../src/lib/state.js";
import { clusterName, randomClusterName, registryHost } from "../../src/lib/names.js";
import { useTempHome } from "../helpers/home.js";

useTempHome();

test("steps are recorded as done", () => {
  expect(isDone("cluster")).toBe(false);
  markDone("cluster");
  expect(isDone("cluster")).toBe(true);
});

test("state starts at version 1 with a stable cluster name", () => {
  expect(loadState().version).toBe(1);
  expect(loadState().clusterName).toBe(loadState().clusterName);
});

test("random cluster names look like adjective-bread", () => {
  expect(randomClusterName()).toMatch(/^[a-z]+-[a-z]+$/);
});

test("registry host follows the cluster name", () => {
  expect(registryHost()).toBe(`${clusterName()}-control-plane:30001`);
});
