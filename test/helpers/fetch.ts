// Scripted fetch stub: routes "METHOD path" to canned responses and records every call
import { vi } from "vitest";

export type Route = { status: number; body?: unknown };
export type Call = { method: string; path: string; body?: unknown };

export function stubFetch(routes: Record<string, Route | ((call: Call) => Route)>) {
  const calls: Call[] = [];
  const fn = vi.fn(async (url: string | URL, init: RequestInit = {}) => {
    const u = new URL(String(url));
    const method = (init.method ?? "GET").toUpperCase();
    const path = u.pathname + u.search;
    const body = typeof init.body === "string" ? JSON.parse(init.body) : undefined;
    const call = { method, path, body };
    calls.push(call);
    const key = Object.keys(routes).find((k) => {
      const [m, p] = k.split(" ");
      return m === method && (p.endsWith("*") ? path.startsWith(p.slice(0, -1)) : path === p);
    });
    const r = key ? routes[key] : { status: 404 };
    const route = typeof r === "function" ? r(call) : r;
    return new Response(route.body === undefined ? null : JSON.stringify(route.body), { status: route.status });
  });
  return { fn: fn as unknown as typeof fetch, calls };
}
