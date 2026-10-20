// Shared step contract: every install step is an idempotent unit with an id
import type { Logger } from "../lib/log.js";
import type { Secrets } from "../lib/secrets.js";

export type Ctx = { secrets: Secrets; log: Logger; arch: "arm64" | "amd64" };

export type Step = { id: string; title: string; run(ctx: Ctx): Promise<void> };
