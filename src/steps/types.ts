// Shared step contract: every install step is an idempotent unit with an id
import type { Logger } from "../lib/log.js";
import type { Secrets } from "../lib/secrets.js";

// ml is true when this lab installs the optional ML layer (install --with-ml, remembered in state)
export type Ctx = { secrets: Secrets; log: Logger; arch: "arm64" | "amd64"; ml?: boolean };

export type Step = { id: string; title: string; run(ctx: Ctx): Promise<void> };
