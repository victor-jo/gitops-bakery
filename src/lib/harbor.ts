// Harbor REST client: projects, robot accounts and repository tags
export class Harbor {
  private readonly auth: string;

  constructor(
    private readonly baseUrl: string,
    user: string,
    password: string,
    private readonly fetchFn: typeof fetch = fetch,
  ) {
    this.auth = "Basic " + Buffer.from(`${user}:${password}`).toString("base64");
  }

  private async call(method: string, path: string, body?: unknown, okStatuses: number[] = []): Promise<Response> {
    const res = await this.fetchFn(`${this.baseUrl}/api/v2.0${path}`, {
      method,
      headers: { authorization: this.auth, "content-type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!res.ok && !okStatuses.includes(res.status))
      throw new Error(`Harbor ${method} ${path} failed: ${res.status} ${await res.text()}`);
    return res;
  }

  async ensureProject(name: string, isPublic: boolean): Promise<void> {
    const head = await this.call("HEAD", `/projects?project_name=${encodeURIComponent(name)}`, undefined, [404]);
    if (head.status === 200) return;
    await this.call("POST", "/projects", { project_name: name, metadata: { public: String(isPublic) } });
  }

  // Harbor never returns a robot's secret again, so an existing robot is replaced to obtain a fresh one
  async ensureRobot(project: string, name: string): Promise<{ name: string; secret: string }> {
    const fullName = `robot$${project}+${name}`;
    const list = (await (await this.call("GET", `/robots?q=${encodeURIComponent(`name=${fullName}`)}`)).json()) as {
      id: number;
      name: string;
    }[];
    for (const r of list.filter((r) => r.name === fullName)) await this.call("DELETE", `/robots/${r.id}`);
    const created = (await (
      await this.call("POST", "/robots", {
        name,
        level: "project",
        duration: -1,
        permissions: [
          {
            kind: "project",
            namespace: project,
            access: [
              { resource: "repository", action: "push" },
              { resource: "repository", action: "pull" },
            ],
          },
        ],
      })
    ).json()) as { name: string; secret: string };
    return { name: created.name, secret: created.secret };
  }

  // Bad credentials get 401 even on a public project, so a 200 proves the stored robot secret still works
  async robotWorks(project: string, robotName: string, secret: string): Promise<boolean> {
    const auth = "Basic " + Buffer.from(`${robotName}:${secret}`).toString("base64");
    const res = await this.fetchFn(`${this.baseUrl}/api/v2.0/projects/${project}/repositories`, { headers: { authorization: auth } });
    return res.ok;
  }

  async listTags(project: string, repo: string): Promise<string[]> {
    const res = await this.call("GET", `/projects/${project}/repositories/${encodeURIComponent(repo)}/artifacts?with_tag=true`, undefined, [404]);
    if (res.status === 404) return [];
    const artifacts = (await res.json()) as { tags: { name: string }[] | null }[];
    return artifacts.flatMap((a) => (a.tags ?? []).map((t) => t.name));
  }

  async deleteRepository(project: string, repo: string): Promise<void> {
    await this.call("DELETE", `/projects/${project}/repositories/${encodeURIComponent(repo)}`, undefined, [404]);
  }
}
