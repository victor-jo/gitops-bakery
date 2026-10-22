# gitops-bakery — Design

## Intent

A laptop-sized GitOps lab that anyone can stand up with one command, and then drive with natural language through their AI assistant.

It packages a stack that was first built by hand in `~/dev/infra/ml-kind-k8s`: kind, Harbor, GitLab + Runner (BuildKit), Argo CD (App of Apps), Prometheus + Grafana. That build hit nine non-obvious traps; the installer's main value is that every one of them is already handled.

**Success moment.** Right after install, the user tells Claude Code "make a FastAPI app and deploy it with GitOps". Claude, through this project's MCP tools, then does three things and returns the app's URL.
1. Creates the source and manifest repos in GitLab.
2. Adds CI that builds and pushes the image to Harbor.
3. Registers the app with Argo CD.

## Goals (v0.1)

1. `npx github:victor-jo/gitops-bakery install` brings up the full stack on a fresh Docker, with no sudo and no manual step.
2. Re-running `install` is safe. It skips finished steps and resumes after a failure.
3. Install also registers a Claude Code skill and an MCP server.
4. The MCP server can create, inspect and delete a GitOps app end to end.
5. Once CI commits the new tag to the manifest repo, the cluster picks it up within 60 seconds instead of waiting for the 3-minute poll. The full loop, from source push to the new version on screen, is measured and reported but has no fixed target, because CI alone took 34–81 s in the original lab.
6. The repository is public at `github.com/victor-jo/gitops-bakery`, with README in English (`README.md`) and Korean (`README.ko.md`).

## Non-goals (v0.1)

- ML components (MLflow, KServe), which are on the roadmap.
- Claude Code is the only AI tool supported. Codex, Cursor and Gemini CLI come later.
- Linux is not guaranteed yet; v0.1 targets macOS arm64.
- No npm publish yet; install is from GitHub.
- Not hardened for production. No TLS, no SSO, single replicas.

## Anti-goals

- An installer that "works on my machine" only after hand fixes. Every trap must be handled in code.
- Hardcoded shared passwords. The original lab used `Harbor12345` and similar.
- Silently touching things outside the lab, such as other kind clusters, the user's global AI config beyond the one MCP entry and one skill folder, or ports outside the declared set.
- MCP tools that leak secrets into the conversation.

## Constraints

- **Host.** macOS on Apple Silicon with OrbStack or Docker Desktop. The Docker VM needs roughly 10 GiB free memory, because the stack measured about 8 GiB across 4 nodes.
- **Harbor** official images are amd64-only and run under Rosetta emulation. This was verified on OrbStack.
- **Garage** is AGPL-3.0. Its Helm chart is not vendored; the installer clones tag `v2.2.0` at install time.
- **Pinned versions,** all known to work together in the original lab:

| Component | Version |
|---|---|
| kindest/node | v1.37.0 |
| Harbor chart | 1.19.4 |
| Argo CD chart | 10.10.5 |
| GitLab chart | 10.5.0 (GitLab 19.5.0 CE) |
| GitLab Runner chart | 0.94.0 |
| CloudNativePG | v1.30.1, PG 17 |
| Valkey chart | 0.12.0 |
| Garage | v2.2.0, image `dxflrs/garage` |
| kube-prometheus-stack | 92.10.1 |
| BuildKit | moby/buildkit v0.34.0-rootless |

- **Repo rules.** Code comments are in English, and every new source file starts with a one-line role comment. No spec or ticket numbers in comments. Commits are semantic and carry no AI attribution. Keep `checklist.md` and `context-notes.md` current.

## Decided by the user

- The name is `gitops-bakery`, after the bread-factory analogy in the original blog post.
- It is a single TypeScript npm package that provides both the CLI and a stdio MCP server.
- Claude Code is supported first, through a skill plus `claude mcp add`.
- macOS arm64 is guaranteed first.
- The code lives in `~/dev/infra/gitops-bakery`.
- Docs are written in English and Korean.
- The GitHub repo becomes public after verification; npm comes later.
- The first scenario is "one app, deployed with GitOps".

## Decided by the designer (open to change)

### CLI
- The binaries are `gitops-bakery` and the alias `bakery`.
- Subcommands:
  - `install` runs preflight, cluster, stack, bootstrap, then the Claude integration.
  - `status` prints component health and URLs.
  - `credentials` prints the usernames and the path to the secrets file.
  - `doctor` runs preflight only.
  - `uninstall` deletes the cluster and removes the MCP entry and skill. It asks for confirmation unless `--yes` is given.
  - `mcp` starts the stdio MCP server.
- External tools are invoked as processes: `docker`, `kind`, `helm`, `kubectl`, `git`. `doctor` reports any missing tool and how to install it, but does not install it.

### State and secrets
- State lives in `~/.gitops-bakery/state.json`. It records the steps done and the generated endpoints.
- Secrets live in `~/.gitops-bakery/secrets.json` with mode 600. They are generated randomly at first install and reused after that.
- **The cluster name is random,** chosen at first install the way Docker names containers. It is `<adjective>-<bread>`, for example `crusty-baguette`, and is stored in `state.json`. Every later command reads it from there. The registry host seen by nodes and pods is `<cluster>-control-plane:30001`. Only one cluster per machine is supported, since the host ports are fixed. *(Decided by the user, 2026-10-20.)*

### Ports
- All ports are mapped through kind `extraPortMappings` with `listenAddress: 127.0.0.1`.

| Host | Purpose |
|---|---|
| 80 | GitLab, mapped to its webservice NodePort |
| 30001 | Harbor |
| 30002 | Argo CD |
| 30004 | Grafana |
| 30010–30019 | Apps created through MCP |

- GitLab needs port 80 because `gitlab.yml` holds a bare host and Rails rejects `localhost:PORT`. On OrbStack the Docker daemon binds `127.0.0.1:80` without sudo. This was checked on 2026-10-20 with `docker run -p 127.0.0.1:80:80 nginx:alpine`, which answered 200. That is unlike `kubectl port-forward`, which got `bind: permission denied` as a normal user. Docker Desktop is best effort in v0.1, and `doctor` checks that port 80 is free.

### Traps handled in code

| # | Trap | Fix |
|---|---|---|
| 1 | kind's containerd has no `config_path` | `containerdConfigPatches` plus a mounted `certs.d/<registry>/hosts.toml` (HTTP, skip_verify) on every node |
| 2 | Harbor is amd64-only | Preflight checks that amd64 emulation works (`uname -m` in an amd64 pod) and fails with a clear message otherwise |
| 3 | GitLab chart v10 ships no PG, Redis or S3 | CloudNativePG with `max_locks_per_transaction: "256"` (schema load is one transaction), Valkey, Garage with the multi-arch image; bucket loop uses arrays, not word splitting |
| 4 | GitLab host cannot carry a port | Host is `localhost` on port 80; in-cluster users (Runner, CI, Argo CD) use `http://gitlab-webservice-default.gitlab.svc.cluster.local:8181` and Runner `clone_url` points there |
| 5 | Runner helper image defaults to amd64; rootless BuildKit needs user namespaces | Runner `node_selector kubernetes.io/arch=arm64` (taken from the host arch), pod seccomp `Unconfined`, `BUILDKITD_FLAGS=--oci-worker-no-process-sandbox` |
| 6 | GitLab expands `$` inside variable values, which breaks `robot$...` | CI variables are created with `raw: true` |
| 7 | `registry.enabled: false` only skips pods; Rails still calls the registry API, so project transfer fails | Also set `global.registry.enabled: false` |
| 8 | Manifest repos are written by CI too, so a subtree split diverges | Repos are created and edited only through the GitLab API, never by subtree push |
| 9 | Human clicks (about 1 req/s) disappear on a `rate()` graph | The default dashboard uses a cumulative stat (unit `none`) and `increase(...[1m])` |

### GitOps bootstrap
- GitLab groups: `devops` (projects `platform` and `service`) and `apps` (app projects, created by MCP).
  - `devops/platform` holds `root.yaml`, `apps/monitoring.yaml`, the monitoring values and the dashboards.
  - `devops/service` holds `root.yaml` and one Application per app.
- These two root Applications are the only resources applied by hand, and the installer applies them.
- Repos are public inside the lab, so Argo CD needs no repo credentials.
- **Fast sync after a manifest commit** has to bridge a URL mismatch. Argo CD's GitLab webhook handler matches the payload's project URL (`http://localhost/...`, because the GitLab host is `localhost`) against each Application's `repoURL` (the in-cluster `gitlab-webservice-default...:8181` address). They will probably never match, so a plain webhook would refresh nothing.
  - First task of the bootstrap work: confirm this on the live cluster with a real hook.
  - If the hook does refresh, use it. Enable `allow_local_requests_from_web_hooks_and_services` and add a project hook with a shared secret on each manifest repo.
  - If it does not, the app CI deploy job calls Argo CD's refresh API (`GET /api/v1/applications/<name>?refresh=normal`) right after it pushes the tag. A dedicated Argo CD local account `ci` with only `get` on applications provides the token, stored as a masked, raw CI variable.
  - Either way, Goal 5 is met by an explicit trigger, not by shortening the poll interval. *(Designer's call.)*
- Harbor gets a public project `apps` and a robot account `robot$apps+ci` with push and pull.

### MCP tools (v0.1)

| Tool | Does |
|---|---|
| `bakery_status` | Component health, URLs, usernames, secrets file path. Never returns secret values |
| `bakery_create_app(name, template="fastapi")` | Creates `apps/<name>` and `apps/<name>-manifests`, sets CI variables (raw), pushes the template, allocates a NodePort from 30010–30019, adds `devops/service/apps/<name>.yaml`, refreshes `service-root`, and returns the URL plus a pipeline link. Fast sync comes from the CI refresh call; webhooks do not match the in-cluster repo URLs |
| `bakery_app_status(name)` | Latest pipeline status and jobs, Harbor tags, Argo CD sync and health, URL |
| `bakery_delete_app(name)` | Removes the Application from `devops/service`, then deletes both repos and the Harbor repository |

- `name` must be a DNS label of at most 30 characters. A duplicate name is an error, not an overwrite.

### Skill
- `skills/gitops-bakery/SKILL.md` is copied to `~/.claude/skills/gitops-bakery/`. It teaches:
  - the lab's address rules (in-cluster GitLab URL, registry host, ports);
  - the app flow and which MCP tool to use for each step;
  - the trap table in short form;
  - how to debug: pipeline logs through MCP status, and `kubectl` for pods.

### Claude Code integration
- If `claude` is on PATH, the installer registers the MCP server at user scope. Otherwise it prints the exact command and continues. The command depends on how the CLI was started. *(Designer's call.)*
  - **From a local checkout** (development and pre-release E2E), the entry is `node <abs path>/dist/cli.js mcp`. No network or GitHub access is needed.
  - **From GitHub** (`npx github:victor-jo/gitops-bakery#<tag> install`), the entry is pinned to the same tag: `npx -y github:victor-jo/gitops-bakery#<tag> mcp`. The MCP code then always matches the installer that set up the cluster.
  - `dist/` is not committed. A `prepare` script builds it, which npm runs when installing from git.
- `uninstall` runs `claude mcp remove gitops-bakery` and deletes the skill folder. It also removes the whole `~/.gitops-bakery/` directory, state and secrets included, so a later `install` starts clean and never skips steps for a cluster that no longer exists. *(Designer's call.)*

### Template
- `templates/fastapi` is generalized from the original joke app.
  - The app has FastAPI, a `/healthz` endpoint, `/metrics` through prometheus-fastapi-instrumentator (excluding `/healthz` and `/metrics`), pytest, and a multi-stage Dockerfile with a `test` stage.
  - The CI file is `.gitlab-ci.yml` with test, build (BuildKit rootless, push to Harbor) and deploy (bump `newTag` in the manifest repo) stages.
  - The manifests are a kustomize Deployment, a NodePort Service with a named port `http` and label `app`, and a ServiceMonitor.

### License
- Apache-2.0.

## Left to the builder

- Internal module layout beyond what the plan names, and the logging style.
- How to wait for readiness: polling intervals and timeouts. Timeouts must produce a message that names the component and the last observed state.
- Exact resource requests and limits, kept close to the original lab.
- The README structure, as long as it has quick start, requirements, what gets installed, MCP tools, the trap table and uninstall.

## Verification

- `npm test` runs vitest unit tests. They cover kind config generation, state and secrets handling, MCP tool input validation, and port allocation.
- E2E (`test/e2e/install.e2e.sh`) starts from Docker with no `gitops-bakery` cluster.
  1. `install` completes; all pods are Running or Completed; all Applications are Synced/Healthy.
  2. A second `install` succeeds with every step skipped.
  3. Calling `bakery_create_app hello` through an MCP client turns the pipeline green, and `curl` on the returned URL gives 200. For a follow-up source push, measure both clocks: from the CI tag commit to the new version on screen (must be under 60 s), and from the source push to the new version on screen (reported only).
  4. GitLab login at `http://localhost` works without sudo.
  5. `uninstall --yes` removes the cluster, the MCP entry and the skill folder.
- Manual check: in a new Claude Code session, the prompt "FastAPI 앱 하나 만들어서 GitOps로 배포해 줘" ends with a working URL.

## Things to confirm with the user during the build

- E2E runs on OrbStack only in v0.1.
- E2E needs the existing `ml-k8s` cluster stopped or deleted, because of port and memory conflicts. Ask before touching it.
- Creating the public GitHub repo and pushing is an outward action. Ask right before doing it.
