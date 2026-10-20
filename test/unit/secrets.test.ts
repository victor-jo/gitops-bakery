// Tests for generated secrets: stable, random-looking and private
import { statSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "vitest";
import { loadOrCreateSecrets, updateSecrets } from "../../src/lib/secrets.js";
import { useTempHome } from "../helpers/home.js";

const home = useTempHome();

test("secrets are generated once and reused", () => {
  const a = loadOrCreateSecrets();
  const b = loadOrCreateSecrets();
  expect(a).toEqual(b);
  expect(a.harborAdmin).toMatch(/^[A-Za-z0-9]{24}$/);
});

test("secrets file is readable only by the owner", () => {
  loadOrCreateSecrets();
  expect(statSync(join(home(), "secrets.json")).mode & 0o777).toBe(0o600);
});

test("updateSecrets merges new values", () => {
  loadOrCreateSecrets();
  expect(updateSecrets({ gitlabPat: "x" }).gitlabPat).toBe("x");
  expect(loadOrCreateSecrets().gitlabPat).toBe("x");
});
