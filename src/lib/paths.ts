// Filesystem locations: the per-user bakery home and the package's bundled assets
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const PACKAGE_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");

export function bakeryHome(): string {
  return process.env.GITOPS_BAKERY_HOME ?? join(homedir(), ".gitops-bakery");
}

export function packageRoot(): string {
  return PACKAGE_ROOT;
}

export function assetPath(...p: string[]): string {
  return join(PACKAGE_ROOT, ...p);
}
