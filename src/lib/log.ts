// Console logger for step progress
export type Logger = {
  info(msg: string): void;
  step(title: string, status: "start" | "done" | "skipped" | "failed"): void;
};

const MARK = { start: "…", done: "✓", skipped: "✓", failed: "✗" } as const;

export const consoleLogger: Logger = {
  info: (msg) => console.log(`  ${msg}`),
  step: (title, status) => console.log(`${MARK[status]} ${title}${status === "skipped" ? " (skipped)" : ""}`),
};
