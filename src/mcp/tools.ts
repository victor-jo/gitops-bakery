// MCP tool definitions: lab status plus create, inspect and delete for GitOps apps; outputs never carry secrets
import { z } from "zod";
import { appStatus, createApp, deleteApp, type AppDeps } from "../apps/lifecycle.js";
import { ARGOCD_HOST_URL, GITLAB_HOST_URL, GITLAB_INTERNAL_URL, GRAFANA_HOST_URL, HARBOR_HOST_URL } from "../lib/config.js";
import { registryHost } from "../lib/names.js";
import { secretsPath } from "../lib/secrets.js";
import { loadState } from "../lib/state.js";
import type { StatusReport } from "../lib/status.js";

type Text = { content: { type: "text"; text: string }[] };
export type ToolDef = {
  name: string;
  description: string;
  inputSchema: z.ZodObject;
  handler(input: Record<string, unknown>): Promise<Text>;
};

const appName = z
  .string()
  .regex(/^[a-z]([a-z0-9-]{0,28}[a-z0-9])?$/, "lowercase letters, digits and '-', max 30, starting with a letter")
  .describe("App name, used for the GitLab repos, the Harbor repository, the Argo CD Application and namespace app-<name>");

const text = (value: unknown): Text => ({ content: [{ type: "text", text: JSON.stringify(value, null, 2) }] });

export function buildTools(p: { deps: () => Promise<AppDeps>; status: () => Promise<StatusReport> }): ToolDef[] {
  return [
    {
      name: "bakery_status",
      description: "Show the gitops-bakery lab: pod readiness per namespace, URLs, usernames, created apps, and where passwords are stored.",
      inputSchema: z.object({}),
      async handler() {
        const s = await p.status();
        return text({
          ...s,
          registryInCluster: registryHost(),
          gitlabInCluster: GITLAB_INTERNAL_URL,
          endpoints: {
            gitlab: { url: GITLAB_HOST_URL, user: "root" },
            harbor: { url: HARBOR_HOST_URL, user: "admin" },
            argocd: { url: ARGOCD_HOST_URL, user: "admin" },
            grafana: { url: GRAFANA_HOST_URL, user: "admin" },
          },
          apps: Object.values(loadState().apps).map((a) => ({ name: a.name, url: `http://localhost:${a.nodePort}` })),
          passwordsFile: secretsPath(),
        });
      },
    },
    {
      name: "bakery_create_app",
      description:
        "Create a new app and deploy it with GitOps: GitLab repos apps/<name> and apps/<name>-manifests, CI that tests, builds to Harbor and bumps the manifest tag, and an Argo CD Application. Returns the app URL and pipeline link; the first pipeline takes about a minute.",
      inputSchema: z.object({ name: appName, template: z.enum(["fastapi"]).default("fastapi") }),
      async handler(input) {
        return text(await createApp(await p.deps(), input.name as string, (input.template as "fastapi") ?? "fastapi"));
      },
    },
    {
      name: "bakery_app_status",
      description: "Show an app's latest pipeline and jobs, Harbor image tags, Argo CD sync and health, and its URL.",
      inputSchema: z.object({ name: appName }),
      async handler(input) {
        return text(await appStatus(await p.deps(), input.name as string));
      },
    },
    {
      name: "bakery_delete_app",
      description: "Delete an app: its Argo CD Application, both GitLab repos and its Harbor repository.",
      inputSchema: z.object({ name: appName }),
      async handler(input) {
        await deleteApp(await p.deps(), input.name as string);
        return text({ deleted: input.name });
      },
    },
  ];
}
