// Polls a readiness check until it passes, failing with the last observed state
export async function waitFor(
  desc: string,
  check: () => Promise<{ ok: boolean; state: string }>,
  timeoutMs: number,
  intervalMs = 5000,
): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  let last = "not checked yet";
  for (;;) {
    try {
      const r = await check();
      if (r.ok) return;
      last = r.state;
    } catch (e) {
      last = (e as Error).message;
    }
    if (Date.now() >= deadline) throw new Error(`Timed out waiting for ${desc}; last state: ${last}`);
    await new Promise((r) => setTimeout(r, intervalMs));
  }
}
