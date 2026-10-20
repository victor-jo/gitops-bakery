// GitLab REST client: groups, projects, commits, CI variables, tokens, hooks and pipelines
export type Pipeline = { id: number; status: string; webUrl: string; jobs: { name: string; status: string }[] };

const enc = encodeURIComponent;

export class GitLab {
  constructor(
    private readonly baseUrl: string,
    private readonly token: string,
    private readonly fetchFn: typeof fetch = fetch,
  ) {}

  private async call<T>(method: string, path: string, body?: unknown, okStatuses: number[] = []): Promise<{ status: number; data: T }> {
    const res = await this.fetchFn(`${this.baseUrl}/api/v4${path}`, {
      method,
      headers: { "PRIVATE-TOKEN": this.token, "content-type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const text = await res.text();
    if (!res.ok && !okStatuses.includes(res.status)) throw new Error(`GitLab ${method} ${path} failed: ${res.status} ${text}`);
    return { status: res.status, data: (text ? JSON.parse(text) : undefined) as T };
  }

  async ensureGroup(path: string): Promise<number> {
    const got = await this.call<{ id: number }>("GET", `/groups/${enc(path)}`, undefined, [404]);
    if (got.status === 200) return got.data.id;
    return (await this.call<{ id: number }>("POST", "/groups", { name: path, path, visibility: "public" })).data.id;
  }

  async ensureProject(groupPath: string, name: string): Promise<{ id: number; pathWithNamespace: string }> {
    const full = `${groupPath}/${name}`;
    const got = await this.call<{ id: number; path_with_namespace: string }>("GET", `/projects/${enc(full)}`, undefined, [404]);
    if (got.status === 404) {
      const groupId = await this.ensureGroup(groupPath);
      const created = await this.call<{ id: number; path_with_namespace: string }>("POST", "/projects", {
        name,
        path: name,
        namespace_id: groupId,
        visibility: "public",
        initialize_with_readme: false,
      });
      return { id: created.data.id, pathWithNamespace: created.data.path_with_namespace };
    }
    return { id: got.data.id, pathWithNamespace: got.data.path_with_namespace };
  }

  async commitFiles(project: string, files: { path: string; content: string }[], message: string, branch = "main"): Promise<string> {
    const actions = [];
    for (const f of files) {
      const exists = await this.call("GET", `/projects/${enc(project)}/repository/files/${enc(f.path)}?ref=${branch}`, undefined, [404]);
      actions.push({ action: exists.status === 200 ? "update" : "create", file_path: f.path, content: f.content });
    }
    const res = await this.call<{ id: string }>("POST", `/projects/${enc(project)}/repository/commits`, {
      branch,
      commit_message: message,
      actions,
    });
    return res.data.id;
  }

  async setVariable(project: string, key: string, value: string, o: { raw: true; masked: boolean }): Promise<void> {
    const body = { key, value, raw: o.raw, masked: o.masked };
    const res = await this.call<{ message?: unknown }>("POST", `/projects/${enc(project)}/variables`, body, [400, 409]);
    if (res.status === 201 || res.status === 200) return;
    if (!JSON.stringify(res.data ?? "").includes("already been taken"))
      throw new Error(`GitLab could not set ${key}: ${JSON.stringify(res.data)}`);
    await this.call("PUT", `/projects/${enc(project)}/variables/${enc(key)}`, body);
  }

  async createProjectToken(project: string, name: string, scopes: string[]): Promise<string> {
    const expires = new Date(Date.now() + 364 * 24 * 3600 * 1000).toISOString().slice(0, 10);
    const res = await this.call<{ token: string }>("POST", `/projects/${enc(project)}/access_tokens`, {
      name,
      scopes,
      access_level: 40,
      expires_at: expires,
    });
    return res.data.token;
  }

  async addHook(project: string, url: string, secret: string): Promise<void> {
    const hooks = (await this.call<{ url: string }[]>("GET", `/projects/${enc(project)}/hooks`)).data;
    if (hooks.some((h) => h.url === url)) return;
    await this.call("POST", `/projects/${enc(project)}/hooks`, { url, token: secret, push_events: true, enable_ssl_verification: false });
  }

  async latestPipeline(project: string): Promise<Pipeline | null> {
    const list = (await this.call<{ id: number; status: string; web_url: string }[]>("GET", `/projects/${enc(project)}/pipelines?per_page=1`)).data;
    if (!list.length) return null;
    const p = list[0];
    const jobs = (await this.call<{ name: string; status: string }[]>("GET", `/projects/${enc(project)}/pipelines/${p.id}/jobs`)).data;
    return { id: p.id, status: p.status, webUrl: p.web_url, jobs: jobs.map((j) => ({ name: j.name, status: j.status })) };
  }

  async deleteProject(project: string): Promise<void> {
    await this.call("DELETE", `/projects/${enc(project)}`, undefined, [404]);
  }

  async setApplicationSetting(key: string, value: unknown): Promise<void> {
    await this.call("PUT", "/application/settings", { [key]: value });
  }

  async createInstanceRunner(description: string): Promise<string> {
    const res = await this.call<{ token: string }>("POST", "/user/runners", { runner_type: "instance_type", description, run_untagged: true });
    return res.data.token;
  }

  async onlineRunners(): Promise<{ description: string }[]> {
    return (await this.call<{ description: string }[]>("GET", "/runners/all?status=online")).data;
  }

  async currentUser(): Promise<{ username: string }> {
    return (await this.call<{ username: string }>("GET", "/user")).data;
  }
}
