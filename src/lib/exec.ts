// Child-process runner that captures output and raises readable errors
import { spawn } from "node:child_process";

export type ExecResult = { code: number; stdout: string; stderr: string };
export type ExecOptions = { input?: string; cwd?: string; env?: Record<string, string>; allowFail?: boolean };

export class ExecError extends Error {
  constructor(public readonly cmd: string, public readonly result: ExecResult) {
    const tail = result.stderr.trim().split("\n").slice(-20).join("\n");
    super(`Command failed (exit ${result.code}): ${cmd}\n${tail}`);
  }
}

export function run(cmd: string, args: string[], opts: ExecOptions = {}): Promise<ExecResult> {
  return new Promise((resolve, reject) => {
    const child = spawn(cmd, args, { cwd: opts.cwd, env: { ...process.env, ...opts.env } });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (d) => (stdout += d));
    child.stderr.on("data", (d) => (stderr += d));
    child.on("error", reject);
    child.on("close", (code) => {
      const result = { code: code ?? 1, stdout, stderr };
      if (result.code !== 0 && !opts.allowFail) reject(new ExecError([cmd, ...args].join(" "), result));
      else resolve(result);
    });
    child.stdin.end(opts.input ?? "");
  });
}
