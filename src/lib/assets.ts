// Reads a bundled asset file and renders its {{var}} placeholders
import { readFileSync } from "node:fs";
import { assetPath } from "./paths.js";
import { render } from "./template.js";

export function asset(relPath: string, vars: Record<string, string | number> = {}): string {
  return render(readFileSync(assetPath("assets", relPath), "utf8"), vars);
}
