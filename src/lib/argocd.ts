// Argo CD REST client: session login, application status and on-demand refresh
// revisions is filled instead of revision for multi-source Applications
export type AppStatus = { sync: string; health: string; revision: string; revisions?: string[]; reconciledAt: string };

export class ArgoCD {
  constructor(
    private readonly baseUrl: string,
    private readonly token: string,
    private readonly fetchFn: typeof fetch = fetch,
  ) {}

  static async login(baseUrl: string, username: string, password: string, fetchFn: typeof fetch = fetch): Promise<ArgoCD> {
    const res = await fetchFn(`${baseUrl}/api/v1/session`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    if (!res.ok) throw new Error(`Argo CD login failed: ${res.status} ${await res.text()}`);
    return new ArgoCD(baseUrl, ((await res.json()) as { token: string }).token, fetchFn);
  }

  private async get(path: string): Promise<Response> {
    return this.fetchFn(`${this.baseUrl}/api/v1${path}`, { headers: { authorization: `Bearer ${this.token}` } });
  }

  async getApp(name: string): Promise<AppStatus | null> {
    const res = await this.get(`/applications/${encodeURIComponent(name)}`);
    if (res.status === 404 || res.status === 403) return null;
    if (!res.ok) throw new Error(`Argo CD get ${name} failed: ${res.status}`);
    const a = (await res.json()) as {
      status?: { sync?: { status?: string; revision?: string; revisions?: string[] }; health?: { status?: string }; reconciledAt?: string };
    };
    return {
      sync: a.status?.sync?.status ?? "Unknown",
      health: a.status?.health?.status ?? "Unknown",
      revision: a.status?.sync?.revision ?? "",
      revisions: a.status?.sync?.revisions ?? [],
      reconciledAt: a.status?.reconciledAt ?? "",
    };
  }

  async refresh(name: string): Promise<void> {
    const res = await this.get(`/applications/${encodeURIComponent(name)}?refresh=normal`);
    if (!res.ok) throw new Error(`Argo CD refresh ${name} failed: ${res.status}`);
  }
}
