// Minimal MCP client for E2E: calls the bakery tools over stdio exactly as Claude Code would
// usage: node test/e2e/mcp-client.mjs <status|create|app-status|delete|wait> [name]
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const [cmd, name] = process.argv.slice(2);
const cli = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "dist", "cli.js");
const client = new Client({ name: "bakery-e2e", version: "0.1.0" });
await client.connect(new StdioClientTransport({ command: "node", args: [cli, "mcp"] }));

async function call(tool, args = {}) {
  const res = await client.callTool({ name: tool, arguments: args });
  const text = res.content.map((c) => c.text).join("\n");
  if (res.isError) throw new Error(`${tool} failed: ${text}`);
  return JSON.parse(text);
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
try {
  if (cmd === "status") console.log(JSON.stringify(await call("bakery_status"), null, 2));
  else if (cmd === "create") console.log(JSON.stringify(await call("bakery_create_app", { name }), null, 2));
  else if (cmd === "app-status") console.log(JSON.stringify(await call("bakery_app_status", { name }), null, 2));
  else if (cmd === "delete") console.log(JSON.stringify(await call("bakery_delete_app", { name }), null, 2));
  else if (cmd === "wait") {
    // Waits until the pipeline succeeded, Argo CD is Synced/Healthy and the URL answers with this app's name
    const deadline = Date.now() + 15 * 60_000;
    for (;;) {
      const s = await call("bakery_app_status", { name });
      const pipeline = s.pipeline?.status ?? "none";
      let body = "";
      if (s.url) body = await fetch(s.url).then((r) => (r.ok ? r.text() : `HTTP ${r.status}`), (e) => e.message);
      console.log(`${new Date().toISOString()} pipeline=${pipeline} argo=${s.sync}/${s.health} url=${body.slice(0, 80)}`);
      if (pipeline === "failed") throw new Error(`pipeline failed: ${s.pipeline.webUrl}`);
      if (pipeline === "success" && s.sync === "Synced" && s.health === "Healthy" && body.includes(`"app":"${name}"`)) break;
      if (Date.now() > deadline) throw new Error("timed out waiting for the app");
      await sleep(10_000);
    }
  } else throw new Error(`unknown command ${cmd}`);
} finally {
  await client.close();
}
