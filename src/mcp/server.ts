// stdio MCP server exposing the bakery tools to Claude Code
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { statusReport } from "../lib/status.js";
import { liveDeps } from "./deps.js";
import { buildTools } from "./tools.js";

export async function startMcpServer(): Promise<void> {
  const server = new McpServer({ name: "gitops-bakery", version: "0.1.0" });
  for (const tool of buildTools({ deps: liveDeps, status: statusReport })) {
    server.registerTool(tool.name, { description: tool.description, inputSchema: tool.inputSchema }, async (input: unknown) => {
      try {
        return await tool.handler((input ?? {}) as Record<string, unknown>);
      } catch (e) {
        return { content: [{ type: "text" as const, text: (e as Error).message }], isError: true };
      }
    });
  }
  await server.connect(new StdioServerTransport());
}
