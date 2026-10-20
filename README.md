# gitops-bakery

**One command bakes a full GitOps lab on your laptop. Then you run it by talking to Claude Code.**

[한국어](README.ko.md)

```bash
npx github:victor-jo/gitops-bakery#v0.1.0 install
```

About 11 minutes later you have a kind cluster with these components, all wired together:

- GitLab and GitLab Runner;
- Harbor;
- Argo CD (App of Apps);
- Prometheus and Grafana.

Claude Code gets a skill and an MCP server for the lab. Then ask:

> "Make a FastAPI app and deploy it with GitOps."

Claude creates the GitLab repos, the CI pipeline (test → rootless BuildKit build → push to Harbor → bump the manifest tag), and the Argo CD Application. It then hands you a URL that serves your app about a minute and a half later.

## Why

Every tool here has a good tutorial on its own. The trouble starts when you connect them:

- which name each side uses for the registry;
- how a CI pod builds images without a Docker daemon;
- why the new version takes three minutes to show up.

This project grew out of building that stack by hand and hitting [nine traps](docs/traps.md). The installer handles every one of them, so you start experimenting instead of debugging.

## Requirements

| | |
|---|---|
| Machine | macOS on Apple Silicon (v0.1 is verified only there) |
| Docker | [OrbStack](https://orbstack.dev) with **at least 10 GiB of memory**. Docker Desktop is best effort. |
| CLIs on `PATH` | `kind`, `helm`, `kubectl`, `git`, Node.js ≥ 20 |
| Free ports on 127.0.0.1 | 80, 30001, 30002, 30004, 30010–30019 |
| Optional | [Claude Code](https://claude.com/claude-code) (`claude` on `PATH`) for the skill and MCP server |

Check your machine first:

```bash
npx github:victor-jo/gitops-bakery#v0.1.0 doctor
```

## What gets installed

| Component | URL | User |
|---|---|---|
| GitLab CE 19.5 | http://localhost | `root` |
| Harbor 2.15 | http://localhost:30001 | `admin` |
| Argo CD 3.5 | http://localhost:30002 | `admin` |
| Grafana | http://localhost:30004 | `admin` |
| Your apps | http://localhost:30010 – 30019 | |

- **Passwords** are generated at install time and stored in `~/.gitops-bakery/secrets.json` (mode 600). `gitops-bakery credentials` tells you where.
- **The cluster** gets a random name the way Docker names containers, for example `airy-scone` or `golden-danish`.
- **Under the hood:**
  - kind (1 control plane + 3 workers);
  - CloudNativePG (PostgreSQL 17), Valkey and Garage (S3) as GitLab's database, Redis and object storage;
  - GitLab Runner with the Kubernetes executor and rootless BuildKit;
  - two Argo CD root Applications that read the GitLab repos `devops/platform` (monitoring) and `devops/service` (your apps).

Only those two root Applications are applied by hand. Everything else, including later changes to monitoring, flows through git.

## Try it

In a new Claude Code session:

```
Make a FastAPI app called hello and deploy it with GitOps.
```

```
What's the status of hello? Show me the pipeline and the image tags.
```

```
Change hello's root endpoint to also return the current time, push it, and tell me when the new version is live.
```

Open Grafana at http://localhost:30004. Its home dashboard counts requests to every app.

## MCP tools

| Tool | What it does |
|---|---|
| `bakery_status` | Pod readiness per namespace, URLs, usernames, the in-cluster registry name, your apps, and the secrets file path |
| `bakery_create_app` | Creates `apps/<name>` and `apps/<name>-manifests` in GitLab, raw CI variables, the FastAPI template, a NodePort from 30010–30019, and the Argo CD Application |
| `bakery_app_status` | Latest pipeline and jobs, Harbor tags, Argo CD sync and health, and the URL |
| `bakery_delete_app` | Removes the Application, both repos and the Harbor repository |

Tool output never contains passwords or tokens. Details are in [docs/mcp-tools.md](docs/mcp-tools.md).

## Commands

```
gitops-bakery install [--force]   # create or resume the lab (safe to rerun)
gitops-bakery status              # pod readiness and URLs
gitops-bakery credentials         # usernames and where the passwords are
gitops-bakery doctor              # preflight checks only
gitops-bakery uninstall [--yes]   # delete the cluster, MCP entry, skill and ~/.gitops-bakery
gitops-bakery mcp                 # MCP server on stdio (Claude Code runs this)
```

`bakery` is a short alias.

## Measured on an M-series MacBook with OrbStack

| | |
|---|---|
| Fresh install | 676 s |
| `bakery_create_app` → app serving | 92 s |
| Source push → new version live | 45–72 s |
| CI tag commit → new version live | 4–13 s |
| Memory across the 4 nodes | about 7.8 GiB |

The tag-to-live time is short because CI asks Argo CD to refresh right after it pushes. GitLab's webhooks don't help here. They carry `http://localhost/...` URLs, which never match the in-cluster repo URLs Argo CD tracks. See [docs/architecture.md](docs/architecture.md).

## Uninstall

```bash
npx github:victor-jo/gitops-bakery#v0.1.0 uninstall
```

## Roadmap

- ML components: MLflow, KServe, and a "train → serve" template
- Codex, Cursor and Gemini CLI integration
- Linux (amd64) support with CI-run end-to-end tests
- npm release

## License

[Apache-2.0](LICENSE). Garage, which is AGPL-3.0, is not bundled; the installer clones it at install time.
