// Randomly generated lab passwords and tokens, kept in a 0600 file
import { randomInt } from "node:crypto";
import { join } from "node:path";
import { readJson, writeJsonAtomic } from "./fsutil.js";
import { bakeryHome } from "./paths.js";

export type Secrets = {
  harborAdmin: string;
  grafanaAdmin: string;
  valkey: string;
  webhook: string;
  gitlabRootPassword?: string;
  gitlabPat?: string;
  harborRobotSecret?: string;
  argocdCiToken?: string;
  argocdAdmin?: string;
  jupyterToken?: string;
};

const ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";

export function randomSecret(length = 24): string {
  let out = "";
  for (let i = 0; i < length; i++) out += ALPHABET[randomInt(ALPHABET.length)];
  return out;
}

export function secretsPath(): string {
  return join(bakeryHome(), "secrets.json");
}

export function loadOrCreateSecrets(): Secrets {
  const existing = readJson<Secrets>(secretsPath());
  if (existing) return existing;
  const fresh: Secrets = {
    harborAdmin: randomSecret(),
    grafanaAdmin: randomSecret(),
    valkey: randomSecret(),
    webhook: randomSecret(),
  };
  writeJsonAtomic(secretsPath(), fresh, 0o600);
  return fresh;
}

export function updateSecrets(patch: Partial<Secrets>): Secrets {
  const next = { ...loadOrCreateSecrets(), ...patch };
  writeJsonAtomic(secretsPath(), next, 0o600);
  return next;
}
