# gitops-bakery v0.1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A single npm package whose `install` brings up kind + Harbor + GitLab/Runner + Argo CD + Prometheus/Grafana on macOS arm64 without sudo, then registers a Claude Code skill and an MCP server that can create, inspect and delete GitOps apps.

**Architecture:**
- A TypeScript CLI (`commander`) runs an ordered list of idempotent steps. Each step shells out to `kind`, `helm`, `kubectl` and `git`, or calls the GitLab, Harbor and Argo CD HTTP APIs, and records completion in `~/.gitops-bakery/state.json`.
- Helm values, kind config, GitOps repo contents and the app template are text assets rendered with `{{var}}` placeholders.
- The same package serves a stdio MCP server whose tools reuse the app lifecycle module.

**Tech Stack:**
- Node ≥ 20 and TypeScript 5 (`tsc`, ESM)
- `commander`, `@modelcontextprotocol/sdk`, `zod`, `yaml`, `vitest`
- External CLIs: docker (OrbStack), kind, helm, kubectl, git

**Spec:** `docs/superpowers/specs/2026-10-20-gitops-bakery-design.md`

**Reference lab (read-only):** `~/dev/infra/ml-kind-k8s`. Its `context-notes.md` holds the raw errors and exact commands behind every trap; its `platform/`, `gitops/`, `apps/` hold working values and manifests to port.

## Global Constraints

- **Pinned versions:**

| Component | Version |
|---|---|
| kindest/node | v1.37.0 |
| Harbor chart | 1.19.4 |
| Argo CD chart | 10.10.5 |
| GitLab chart | 10.5.0 |
| GitLab Runner chart | 0.94.0 |
| CloudNativePG | v1.30.1, PG 17 |
| Valkey chart | 0.12.0 |
| Garage | v2.2.0, cloned at install time, image `dxflrs/garage` |
| kube-prometheus-stack | 92.10.1 |
| BuildKit | `moby/buildkit:v0.34.0-rootless` |

- **Names:**
  - Cluster `gitops-bakery`; registry host `gitops-bakery-control-plane:30001`.
  - In-cluster GitLab URL `http://gitlab-webservice-default.gitlab.svc.cluster.local:8181`.
  - GitLab host `localhost`.
- **Host ports**, all on `127.0.0.1`: 80 GitLab, 30001 Harbor, 30002 Argo CD, 30004 Grafana, 30010–30019 apps.
- **Files:** state in `~/.gitops-bakery/state.json` and secrets in `~/.gitops-bakery/secrets.json` (mode 600). The env var `GITOPS_BAKERY_HOME` overrides the directory and is used by tests.
- **Secrets:** no hardcoded passwords. Generate each at first install: 24 characters from `[A-Za-z0-9]`.
- **GitLab groups and repos:**
  - `devops/platform` and `devops/service` (bootstrap);
  - for each app, `apps/<name>` and `apps/<name>-manifests`.
  - Harbor public project `apps`, robot `robot$apps+ci`.
- **App names** are DNS labels: `^[a-z]([a-z0-9-]{0,28}[a-z0-9])?$`, at most 30 characters.
- **Code style:**
  - Code comments are in English, and every new source file starts with a one-line English role comment.
  - No spec or ticket numbers in comments.
  - Semantic commits with no AI attribution trailer.
  - Update `checklist.md` and `context-notes.md` in every task.
- **Garage chart is AGPL:** never vendor it into this repo.

## Review Focus

1. **Re-running `install` after a failure part-way through a step** (a helm release exists but is not ready). The run should resume and finish, not fail with "cannot re-use a name". Pinned in Task 3 by `runner resumes after a failed step` and by using `helm upgrade --install` everywhere (Task 4).
2. **A required host port already taken,** for example by the old `ml-k8s` cluster on 30001. `install` should stop before creating anything and name the port. Pinned in Task 2 by `preflight reports busy ports`.
3. **Bad app requests:** an invalid name, a duplicate name, or an 11th app when the 10-port pool is full. Each should fail with a clear message and create nothing. Pinned in Task 9.
4. **Secret values reaching the AI conversation.** No MCP tool output may contain any value from `secrets.json`. Pinned in Task 10 by `tool outputs never contain secret values`.
5. **`claude` CLI not installed.** `install` should still succeed and print the exact `claude mcp add …` command. Pinned in Task 10.

---

### Task 1: Scaffold and core libraries

**Files:**
- Create:
  - `package.json`, `tsconfig.json`, `vitest.config.ts`, `.gitignore` (`node_modules`, `dist`, `.superpowers`)
  - `LICENSE` (Apache-2.0), `checklist.md`, `context-notes.md`
- Create: `src/lib/paths.ts`, `src/lib/config.ts`, `src/lib/template.ts`, `src/lib/state.ts`, `src/lib/secrets.ts`, `src/lib/exec.ts`
- Test: `test/unit/template.test.ts`, `test/unit/state.test.ts`, `test/unit/secrets.test.ts`

**Interfaces:**
- Produces:
  - `paths.ts`:
    - `bakeryHome(): string` reads `GITOPS_BAKERY_HOME`, else `~/.gitops-bakery`.
    - `assetPath(...p: string[]): string` resolves from the package root.
  - `config.ts` holds the constants:
    - `CLUSTER`, `REGISTRY`, `GITLAB_INTERNAL_URL`, `GITLAB_HOST_URL = "http://localhost"`
    - `PORTS = { gitlab: 80, harbor: 30001, argocd: 30002, grafana: 30004, appMin: 30010, appMax: 30019 }`
    - `VERSIONS` (the table above)
  - `template.ts`: `render(text: string, vars: Record<string, string | number>): string`.
  - `state.ts`:
    - Type `State = { version: 1; steps: Record<string, { doneAt: string }>; apps: Record<string, AppRecord>; fastSync?: "webhook" | "ci-refresh" }`
    - Type `AppRecord = { name: string; nodePort: number; createdAt: string }`
    - Functions `loadState(): State`, `saveState(s: State): void`, `markDone(id: string): void`, `isDone(id: string): boolean`
  - `secrets.ts`:
    - Type `Secrets = { harborAdmin: string; grafanaAdmin: string; valkey: string; webhook: string; gitlabRootPassword?: string; gitlabPat?: string; harborRobotSecret?: string; argocdCiToken?: string; argocdAdmin?: string }`
    - Functions `loadOrCreateSecrets(): Secrets`, `updateSecrets(patch: Partial<Secrets>): Secrets`
  - `exec.ts`:
    - `run(cmd: string, args: string[], opts?: { input?: string; cwd?: string; env?: Record<string,string>; allowFail?: boolean }): Promise<{ code: number; stdout: string; stderr: string }>`
    - When `allowFail` is not set, a non-zero exit throws `ExecError`, whose message includes the command and the last 20 lines of stderr.

- [ ] **Step 1: Initialize the npm package.** Set `"type": "module"`, `"bin": {"gitops-bakery": "dist/cli.js", "bakery": "dist/cli.js"}` and `"engines": {"node": ">=20"}`. Add the scripts `build` (`tsc`), `prepare` (`npm run build`) and `test` (`vitest run`). Write `checklist.md` with one section per task here and `context-notes.md` with a header. Commit as `chore: scaffold gitops-bakery package`.
- [ ] **Step 2: Write the failing tests.**

```ts
// template.test.ts
expect(render("img {{registry}}/apps/{{name}}", { registry: "r:1", name: "hello" })).toBe("img r:1/apps/hello");
expect(() => render("{{missing}}", {})).toThrow(/missing/);
// state.test.ts (GITOPS_BAKERY_HOME = fresh tmpdir per test)
expect(isDone("cluster")).toBe(false); markDone("cluster"); expect(isDone("cluster")).toBe(true);
expect(loadState().version).toBe(1);
// secrets.test.ts
const a = loadOrCreateSecrets(); const b = loadOrCreateSecrets();
expect(a).toEqual(b);
expect(a.harborAdmin).toMatch(/^[A-Za-z0-9]{24}$/);
expect(statSync(join(home, "secrets.json")).mode & 0o777).toBe(0o600);
expect(updateSecrets({ gitlabPat: "x" }).gitlabPat).toBe("x");
```

- [ ] **Step 3: Run the tests and see them fail.** `npx vitest run test/unit` → FAIL (modules missing).
- [ ] **Step 4: Implement the six modules.**
  - `render` replaces `/\{\{(\w+)\}\}/g` and throws `Unknown template variable: <name>` when a key is missing.
  - Secrets come from `crypto.randomInt` over the alphabet.
  - Write files atomically: a temp file, then rename.
- [ ] **Step 5: Run the tests and see them pass.** `npm test` → all pass. Also `npm run build` → no tsc errors.
- [ ] **Step 6: Commit.** `feat: add paths, config, template, state, secrets and exec modules`.

### Task 2: kind cluster config, preflight and the cluster step

**Files:**
- Create: `src/kind/config.ts`, `src/steps/preflight.ts`, `src/steps/cluster.ts`, `assets/kind/hosts.toml.tmpl`
- Test: `test/unit/kind-config.test.ts`, `test/unit/preflight.test.ts`

**Interfaces:**
- Consumes `config.ts` and `exec.run`.
- Produces:
  - `kindConfig(opts: { certsDir: string; workers: number }): string` returns YAML.
  - `checkPorts(isFree: (port: number) => Promise<boolean>): Promise<number[]>` returns the busy ports.
  - `preflight(): Promise<PreflightReport>` with `PreflightReport = { ok: boolean; problems: string[] }`. It checks:
    - docker is reachable;
    - `kind`, `helm`, `kubectl` and `git` are on PATH;
    - Docker memory is at least 10 GiB (from `docker info --format '{{.MemTotal}}'`);
    - every port in `PORTS` is free.
  - Step `cluster` (see the `Step` type in Task 3):
    1. Writes `<home>/certs.d/gitops-bakery-control-plane:30001/hosts.toml` from the asset.
    2. Runs `kind create cluster --name gitops-bakery --image kindest/node:v1.37.0 --config -`.
    3. Verifies amd64 emulation. `kubectl run arch-check --rm -i --restart=Never --image=amd64/alpine:3.22 -- uname -m` must print `x86_64`. Otherwise it fails with `Harbor needs amd64 emulation (Rosetta); enable it in OrbStack/Docker Desktop settings`.

- [ ] **Step 1: Write the failing tests.** Parse `kindConfig` output with `yaml` and assert:
  - It has `containerdConfigPatches[0]` containing `config_path = "/etc/containerd/certs.d"`.
  - There are 1 + `workers` nodes, each with an `extraMounts` entry `{hostPath: certsDir, containerPath: "/etc/containerd/certs.d"}`.
  - The control-plane `extraPortMappings` map host ports 80, 30001, 30002, 30004 and 30010–30019. Each has `listenAddress: "127.0.0.1"`. The host-80 entry targets `containerPort: 30080`, the GitLab NodePort, which Task 6 values use.
  - Preflight: `checkPorts(async p => p !== 30001)` resolves to `[30001]`, and `preflight reports busy ports` yields a problem string containing `30001`.
- [ ] **Step 2: Run the tests and see them fail.** `npx vitest run test/unit/kind-config.test.ts test/unit/preflight.test.ts` → FAIL.
- [ ] **Step 3: Implement.**
  - Port the kind config from `ml-kind-k8s/install.sh`.
  - Port `hosts.toml` from `ml-kind-k8s/containerd/certs.d/*/hosts.toml`, with the server set to `http://gitops-bakery-control-plane:30001`.
  - `isFree` default: try `net.createServer().listen(port, "127.0.0.1")`.
- [ ] **Step 4: Run the tests and see them pass.** `npm test` → pass.
- [ ] **Step 5: Commit.** `feat: generate kind config and add preflight checks`.

### Task 3: Step runner and CLI

**Files:**
- Create: `src/steps/types.ts`, `src/steps/runner.ts`, `src/steps/index.ts`, `src/cli.ts`, `src/lib/log.ts`
- Test: `test/unit/runner.test.ts`

**Interfaces:**
- Consumes `state.ts`, `secrets.ts`, and the steps from Tasks 2 and 4–8 (registered in `index.ts` as they land).
- Produces:
  - `type Ctx = { secrets: Secrets; log: Logger; arch: "arm64" | "amd64" }`
  - `type Step = { id: string; title: string; run(ctx: Ctx): Promise<void> }`
  - `runSteps(steps: Step[], ctx: Ctx, opts?: { force?: boolean }): Promise<void>`. It skips steps where `isDone(id)` is true, calls `markDone(id)` after each success, and rethrows after logging `✗ <title>` on failure.
  - `ALL_STEPS: Step[]` in install order: `preflight, cluster, harbor, argocd, cnpg, valkey, garage, gitlab, gitlab-auth, runner, bootstrap, fast-sync, claude`.
  - CLI commands:
    - `install [--force]`
    - `status`, which prints a table of components (pods ready per namespace) and URLs
    - `credentials`, which prints usernames and the path to `secrets.json`, never the values
    - `doctor`
    - `uninstall [--yes]`
    - `mcp`
- `waitFor(desc: string, check: () => Promise<{ ok: boolean; state: string }>, timeoutMs: number, intervalMs = 5000): Promise<void>` goes in `src/lib/wait.ts`. On timeout it throws `Timed out waiting for <desc>; last state: <state>`.

- [ ] **Step 1: Write the failing tests.**

```ts
test("runner skips done steps", ...)        // markDone("a"); a.run never called; b.run called once
test("runner resumes after a failed step")  // b throws on 1st call → rejects; 2nd runSteps: a skipped, b runs, c runs
test("waitFor reports last state on timeout") // check returns {ok:false,state:"Pending"}; rejects /Pending/
```

- [ ] **Step 2: Run the tests and see them fail.** `npx vitest run test/unit/runner.test.ts` → FAIL.
- [ ] **Step 3: Implement** `runner.ts`, `wait.ts`, `log.ts` (step lines like `✓ Harbor (skipped)`), and `cli.ts` with commander.
  - `uninstall` asks `Delete cluster gitops-bakery and ~/.gitops-bakery? [y/N]` unless `--yes`.
  - It then runs `kind delete cluster --name gitops-bakery` and removes `bakeryHome()`. The Claude cleanup is wired in Task 10.
- [ ] **Step 4: Run the tests and see them pass.** `npm test` → pass. Also run `node dist/cli.js doctor`. Right now, with `ml-k8s` running, it should report ports 30001 and 30002 as busy. This checks a Review Focus item against reality.
- [ ] **Step 5: Commit.** `feat: add idempotent step runner and CLI commands`.

### Task 4: Harbor and Argo CD steps

**Files:**
- Create: `src/lib/helm.ts`, `src/lib/k8s.ts`, `src/lib/harbor.ts`, `src/steps/harbor.ts`, `src/steps/argocd.ts`
- Create: `assets/values/harbor.yaml`, `assets/values/argocd.yaml`
- Test: `test/unit/harbor-client.test.ts`

**Interfaces:**
- Produces:
  - `helmUpgrade(o: { release: string; chart: string; version: string; ns: string; repo?: { name: string; url: string }; values: string; timeout?: string }): Promise<void>` always uses `upgrade --install --create-namespace --wait`, and reads values from stdin (`-f -`).
  - `kubectl(args: string[], input?: string): Promise<string>` and `applyYaml(yaml: string): Promise<void>`.
  - Class `Harbor(baseUrl, user, password)`:
    - `ensureProject(name: string, isPublic: boolean): Promise<void>`
    - `ensureRobot(project: string, name: string): Promise<{ name: string; secret: string }>`. It recreates the robot if one exists but its secret is unknown.
    - `listTags(project: string, repo: string): Promise<string[]>`
    - `deleteRepository(project: string, repo: string): Promise<void>`
  - Step `harbor` installs the chart, waits for core to be ready, ensures project `apps` is public, ensures robot `ci`, and stores `harborRobotSecret`.
  - Step `argocd` installs with NodePort 30002, insecure mode and dex off. It stores the `argocdAdmin` password from `argocd-initial-admin-secret`.

- [ ] **Step 1: Write the failing test.** Stub `fetch` with `vi.fn`.
  - `ensureProject` sends `HEAD /api/v2.0/projects?project_name=apps`. On 404 it then sends `POST /api/v2.0/projects` with `{project_name:"apps", metadata:{public:"true"}}`. On 200 it makes no POST.
  - `ensureRobot` sends POST `/api/v2.0/robots` with `permissions[0].access` containing `push` and `pull` on `repository`, and returns `{name:"robot$apps+ci", secret}` from the response.
- [ ] **Step 2: Run the test and see it fail.** `npx vitest run test/unit/harbor-client.test.ts` → FAIL.
- [ ] **Step 3: Implement.**
  - Port values from `ml-kind-k8s/platform/harbor/values.yaml`:
    - `externalURL: http://{{registry}}`;
    - `harborAdminPassword: {{harborAdmin}}`;
    - nodePort 30001, TLS off, trivy off.
  - Port values from `ml-kind-k8s/platform/argocd/values.yaml`.
  - Harbor API base from the host is `http://localhost:30001`.
- [ ] **Step 4: Run the test and see it pass.** `npm test` → pass.
- [ ] **Step 5: Commit.** `feat: install Harbor and Argo CD`.

### Task 5: GitLab dependencies (CloudNativePG, Valkey, Garage)

**Files:**
- Create: `src/steps/cnpg.ts`, `src/steps/valkey.ts`, `src/steps/garage.ts`
- Create: `assets/deps/cnpg-cluster.yaml`, `assets/values/valkey.yaml`, `assets/values/garage.yaml`
- Test: `test/unit/garage-buckets.test.ts`

**Interfaces:**
- Produces:
  - Kubernetes objects in namespace `gitlab`:
    - Secret `gitlab-rails-db-app`, created by CNPG for Cluster `gitlab-rails-db`;
    - Secret `valkey-auth`, key `default-password`;
    - Secrets `gitlab-object-storage` (key `connection`) and `gitlab-object-storage-s3cmd` (key `config`).
  - `GITLAB_BUCKETS: string[]`, the 14 bucket names used by the original lab with the registry bucket excluded.
  - `garageCommands(nodeId: string, buckets: string[]): string[][]`, the argv lists for:
    - `layout assign -z dc1 -c 1G <nodeId>`
    - `layout apply --version 1`
    - one `bucket create` per bucket
    - `key create gitlab`
    - one `bucket allow --read --write --owner <bucket> --key gitlab` per bucket

- [ ] **Step 1: Write the failing test.** `garageCommands("abc", ["a","b"])` has length 2 + 2 + 1 + 2 and every argv is a separate array element. This is how the zsh word-splitting trap is pinned. `GITLAB_BUCKETS` has length 14.
- [ ] **Step 2: Run the test and see it fail.** `npx vitest run test/unit/garage-buckets.test.ts` → FAIL.
- [ ] **Step 3: Implement.**
  - **cnpg:** `kubectl apply --server-side` the v1.30.1 release manifest, wait for the operator, then apply the cluster from `ml-kind-k8s/platform/gitlab/deps/cnpg-cluster.yaml`. Keep `max_locks_per_transaction: "256"`.
  - **valkey:** helm 0.12.0 with `{{valkey}}` as the password.
  - **garage:**
    1. `git clone --depth 1 --branch v2.2.0` into `<home>/cache/garage`.
    2. Helm install `script/helm/garage` with the image `dxflrs/garage`.
    3. Run the `garageCommands` through `kubectl exec garage-0 -- /garage …`.
    4. Build the two Secrets from the key output, following the format of the GitLab bundled-chart migration docs (https://docs.gitlab.com/charts/installation/migration/bundled_chart_migration/).
  - Each step is idempotent. Skip `bucket create` if the bucket already exists, and reuse the key if `key info gitlab` succeeds.
- [ ] **Step 4: Run the test and see it pass.** `npm test` → pass.
- [ ] **Step 5: Commit.** `feat: install CloudNativePG, Valkey and Garage for GitLab`.

### Task 6: GitLab, root token and the GitLab client

**Files:**
- Create: `src/lib/gitlab.ts`, `src/steps/gitlab.ts`, `src/steps/gitlab-auth.ts`, `assets/values/gitlab.yaml`
- Test: `test/unit/gitlab-client.test.ts`

**Interfaces:**
- Produces class `GitLab(baseUrl: string, token: string)` with these methods:
  - `ensureGroup(path: string): Promise<number>` returns the group id.
  - `ensureProject(groupPath: string, name: string): Promise<{ id: number; pathWithNamespace: string }>` creates the project public, with `initialize_with_readme: false`.
  - `commitFiles(project: string, files: { path: string; content: string }[], message: string, branch = "main"): Promise<string>`:
    - returns the commit SHA;
    - uses action `create` or `update` depending on whether the file exists;
    - starts the branch on the first commit.
  - `setVariable(project: string, key: string, value: string, o: { raw: true; masked: boolean }): Promise<void>` upserts the variable.
  - `createProjectToken(project: string, name: string, scopes: string[]): Promise<string>` creates a token with access level Maintainer and a 1-year expiry.
  - `addHook(project: string, url: string, secret: string): Promise<void>`
  - `latestPipeline(project: string): Promise<{ id: number; status: string; webUrl: string; jobs: { name: string; status: string }[] } | null>`
  - `deleteProject(project: string): Promise<void>`
  - `setApplicationSetting(key: string, value: unknown): Promise<void>`
- Step `gitlab` installs the chart with `--timeout 20m`. It waits for the readiness check: `GET http://localhost/-/readiness` returns 200.
- Step `gitlab-auth`:
  - reads `gitlab-gitlab-initial-root-password` into `gitlabRootPassword`;
  - creates a root PAT (scopes `api`) through the toolbox, using `kubectl exec deploy/gitlab-toolbox -- gitlab-rails runner '<ruby>'`, and stores it as `gitlabPat`;
  - verifies the PAT with `GET /api/v4/user`.

- [ ] **Step 1: Write the failing tests.** Use a stubbed `fetch`.
  - `setVariable` sends `raw: true`. On 409, or 400 "has already been taken", it follows with a PUT.
  - `commitFiles` sends `action: "update"` for paths that `GET /repository/files/<path>?ref=main` reports as existing, and `"create"` otherwise.
  - `ensureGroup("devops")` makes no POST when `GET /groups/devops` returns 200.
- [ ] **Step 2: Run the tests and see them fail.** `npx vitest run test/unit/gitlab-client.test.ts` → FAIL.
- [ ] **Step 3: Implement.**
  - Port `ml-kind-k8s/platform/gitlab/values.yaml`.
  - Keep `global.registry.enabled: false`, `hosts.gitlab.name: localhost`, `hosts.https: false`, and ingress, TLS, kas and shell off.
  - Set `gitlab.webservice.service.type: NodePort` with workhorse nodePort `30080` (port 80 on the host maps there).
  - Delete the `# browser reaches GitLab through port-forward` comment.
  - Project paths in the API are URL-encoded (`encodeURIComponent`).
- [ ] **Step 4: Run the tests and see them pass.** `npm test` → pass.
- [ ] **Step 5: Commit.** `feat: install GitLab and add the GitLab API client`.

### Task 7: GitLab Runner

**Files:**
- Create: `src/steps/runner.ts`, `assets/values/gitlab-runner.yaml`
- Test: `test/unit/runner-values.test.ts`

**Interfaces:**
- Consumes `GitLab` and `gitlabPat`.
- Produces a registered instance runner. `POST /api/v4/user/runners` with `runner_type=instance_type` returns a `glrt-` token, which goes into Secret `gitlab-runner/gitlab-runner-token`.

- [ ] **Step 1: Write the failing test.** Render `gitlab-runner.yaml` with `{ arch: "arm64" }`, parse the embedded TOML text, and assert it contains:
  - `clone_url = "http://gitlab-webservice-default.gitlab.svc.cluster.local:8181"`
  - `"kubernetes.io/arch" = "arm64"`
  - `type = "Unconfined"`
- [ ] **Step 2: Run the test and see it fail.** → FAIL.
- [ ] **Step 3: Implement.** Port `ml-kind-k8s/platform/gitlab-runner/values.yaml` with `{{arch}}`. The step skips token creation if the Secret exists, and waits until `GET /api/v4/runners/all` shows the runner `online`.
- [ ] **Step 4: Run the test and see it pass.** `npm test` → pass.
- [ ] **Step 5: Commit.** `feat: register GitLab Runner with arm64 helper and rootless BuildKit support`.

### Task 8: GitOps bootstrap, monitoring and fast sync

**Files:**
- Create: `src/steps/bootstrap.ts`, `src/steps/fast-sync.ts`, `src/lib/argocd.ts`
- Create assets:
  - `assets/gitops/platform/{root.yaml,apps/monitoring.yaml,monitoring/values.yaml,monitoring/dashboards/kustomization.yaml,monitoring/dashboards/requests.json}`
  - `assets/gitops/service/root.yaml`
- Test: `test/unit/gitops-assets.test.ts`

**Interfaces:**
- Consumes `GitLab` and `applyYaml`.
- Produces:
  - Repos `devops/platform` and `devops/service` filled from the assets.
  - Applications `platform-root`, `monitoring` and `service-root`, all Synced/Healthy.
  - Class `ArgoCD(baseUrl, token)`:
    - `getApp(name: string): Promise<{ sync: string; health: string; revision: string } | null>`
    - `refresh(name: string): Promise<void>`
  - The fast-sync mode is stored in `state.fastSync` (`"webhook"` or `"ci-refresh"`). Task 9 reads it through `getFastSyncMode(): "webhook" | "ci-refresh"` in `src/steps/fast-sync.ts`, which throws if the mode is unset.

- [ ] **Step 1: Write the failing test.** Render every gitops asset with test vars and parse it as YAML or JSON. Then assert:
  - The `monitoring.yaml` sources pin `kube-prometheus-stack` at `92.10.1` and include `ServerSideApply=true`.
  - The monitoring values have `alertmanager.enabled: false` and `serviceMonitorSelectorNilUsesHelmValues: false`.
  - The `grafana.ini` home path is `/tmp/dashboards/requests.json`.
  - The dashboard has a `stat` panel with unit `none` and an `increase(` query.
  - The monitoring values set the Grafana service to NodePort `30004`.
  - No `root.yaml` lies under an `apps/` path.
- [ ] **Step 2: Run the test and see it fail.** → FAIL.
- [ ] **Step 3: Implement the bootstrap.**
  - Port from `ml-kind-k8s/gitops/`. Make the dashboard generic: the namespace selector becomes `namespace=~"app-.*"`, because each app is deployed to namespace `app-<name>`.
  - Bootstrap order:
    1. Create the groups.
    2. Create the projects.
    3. `commitFiles` the assets.
    4. Apply both `root.yaml` files.
    5. Wait for all three Applications to be Synced/Healthy (timeout 15 min).
- [ ] **Step 4: Spike for fast sync on the live cluster.** Record the outcome in `context-notes.md` with the raw output.
  1. Enable `allow_local_requests_from_web_hooks_and_services`.
  2. Add a hook on `devops/platform` to `http://argocd-server.argocd.svc.cluster.local/api/webhook`.
  3. Commit a trivial change.
  4. Check whether `platform-root` refreshes within 10 s, looking at `status.reconciledAt`.
  - If it does, set `state.fastSync = "webhook"`, and `fast-sync` adds hooks per repo.
  - If not, set `state.fastSync = "ci-refresh"`, and `fast-sync` does three things:
    - Creates an Argo CD local account `ci` with the `apiKey` capability and RBAC `p, role:ci, applications, get, */*, allow`, via the `argocd-cm` and `argocd-rbac-cm` values in `assets/values/argocd.yaml`. A helm upgrade is fine.
    - Generates its token through `POST /api/v1/account/ci/token`.
    - Stores it as `argocdCiToken`.
- [ ] **Step 5: Run the test and see it pass.** `npm test` → pass, plus a live check that `kubectl -n argocd get applications` shows 3 Synced/Healthy.
- [ ] **Step 6: Commit.** `feat: bootstrap devops repos, monitoring and fast sync`.

### Task 9: App lifecycle and the FastAPI template

**Files:**
- Create: `src/apps/names.ts`, `src/apps/ports.ts`, `src/apps/lifecycle.ts`
- Create template `templates/fastapi/app/**`:
  - `app/main.py`, `tests/test_api.py`
  - `requirements.txt`, `requirements-dev.txt`
  - `Dockerfile`, `.dockerignore`, `.gitlab-ci.yml`
- Create template `templates/fastapi/manifests/**`: `deployment.yaml`, `service.yaml`, `servicemonitor.yaml`, `kustomization.yaml`
- Create: `assets/gitops/service/app.yaml.tmpl`
- Test: `test/unit/apps.test.ts`

**Interfaces:**
- Consumes `GitLab`, `Harbor`, `ArgoCD`, `loadState`/`saveState`, `render`, and `getFastSyncMode()`.
- Produces:
  - `validateAppName(name: string): void` throws `Invalid app name "<n>": use lowercase letters, digits and "-" (max 30)`.
  - `allocatePort(apps: Record<string, AppRecord>): number`. It returns the lowest free port in 30010–30019 and otherwise throws `No free app port (30010-30019 are all used); delete an app first`.
  - `type AppDeps = { gitlab: GitLab; harbor: Harbor; argocd: ArgoCD; secrets: Secrets }`
  - `createApp(deps: AppDeps, name: string, template: "fastapi"): Promise<{ url: string; pipelineUrl: string; repo: string; manifestsRepo: string }>`
  - `appStatus(deps: AppDeps, name: string): Promise<{ pipeline: …; tags: string[]; sync: string; health: string; url: string }>`
  - `deleteApp(deps: AppDeps, name: string): Promise<void>`
- `createApp` does these steps in order:
  1. Validate the name and reject duplicates (`App "<n>" already exists`) before any API call.
  2. Allocate a port.
  3. Create `apps/<name>-manifests` and commit the manifests rendered with `{name, registry, nodePort, image: REGISTRY + "/apps/" + name}`.
  4. Create a project token on the manifests repo.
  5. Create `apps/<name>` and set raw variables:
     - `HARBOR_USER = robot$apps+ci`
     - `HARBOR_PASSWORD` (masked)
     - `MANIFEST_TOKEN` (masked)
     - `ARGOCD_TOKEN` (masked), only when the mode is `ci-refresh`
  6. Commit the app template, which triggers the pipeline.
  7. Commit `apps/<name>.yaml` to `devops/service`, with destination namespace `app-<name>` and `CreateNamespace=true`.
  8. Add hooks when the mode is `webhook`.
  9. Save the `AppRecord`.
  - If any step after step 3 fails, run `deleteApp` before rethrowing, so nothing partial is left.
- The template `.gitlab-ci.yml` is ported from `ml-kind-k8s/apps/joke-api/.gitlab-ci.yml`:
  - Keep the quoted `sed` line.
  - Keep `git pull --rebase` before push.
  - When `ARGOCD_TOKEN` is set, append `curl -fsS -H "Authorization: Bearer $ARGOCD_TOKEN" "http://argocd-server.argocd.svc.cluster.local/api/v1/applications/{{name}}?refresh=normal"`.
- The template app is ported from `ml-kind-k8s/apps/joke-api`. Replace the jokes module with one `GET /` that returns `{"app": "{{name}}", "version": APP_VERSION}`. Keep `/healthz`, `/metrics` and the instrumentator exclusions. Keep 3 tests: root returns name and version, healthz, and metrics excludes probes.

- [ ] **Step 1: Write the failing tests.**

```ts
expect(() => validateAppName("Hello")).toThrow(/Invalid app name/);
expect(() => validateAppName("a".repeat(31))).toThrow();
expect(allocatePort({})).toBe(30010);
expect(allocatePort({ a: { nodePort: 30010 } as AppRecord })).toBe(30011);
// 10 apps → throws /No free app port/
// createApp duplicate: state has "hello" → rejects /already exists/ and the stubbed gitlab has 0 calls
// createApp rollback: stub commitFiles to throw on the app repo → deleteProject called for both repos
// template render: every file under templates/fastapi renders with test vars and leaves no "{{"
```

- [ ] **Step 2: Run the tests and see them fail.** `npx vitest run test/unit/apps.test.ts` → FAIL.
- [ ] **Step 3: Implement** `names.ts`, `ports.ts` and `lifecycle.ts`, plus the template files.
- [ ] **Step 4: Run the tests and see them pass.** `npm test` → pass.
- [ ] **Step 5: Commit.** `feat: add app lifecycle and FastAPI GitOps template`.

### Task 10: MCP server, skill and Claude Code integration

**Files:**
- Create: `src/mcp/server.ts`, `src/mcp/tools.ts`, `src/steps/claude.ts`, `skills/gitops-bakery/SKILL.md`
- Modify: `src/cli.ts`, so that `uninstall` also calls `removeClaudeIntegration()`
- Test: `test/unit/mcp-tools.test.ts`, `test/unit/claude.test.ts`

**Interfaces:**
- Consumes the lifecycle module (Task 9), `loadOrCreateSecrets`, and `loadState`.
- Produces:
  - `buildTools(deps: () => Promise<AppDeps>): ToolDef[]`, where `ToolDef = { name: string; description: string; inputSchema: ZodObject; handler(input): Promise<{ content: { type: "text"; text: string }[] }> }`. The names are `bakery_status`, `bakery_create_app`, `bakery_app_status` and `bakery_delete_app`.
  - `startMcpServer(): Promise<void>` registers the tools on `McpServer` over a `StdioServerTransport`.
  - `mcpCommand(): { command: string; args: string[] }`:
    - If running from a git checkout (a `.git` exists next to `package.json`), it returns `{ command: "node", args: [<abs>/dist/cli.js, "mcp"] }`.
    - Otherwise it returns `{ command: "npx", args: ["-y", "github:victor-jo/gitops-bakery#v" + pkg.version, "mcp"] }`.
  - Step `claude`:
    1. Copies `skills/gitops-bakery` to `~/.claude/skills/gitops-bakery`.
    2. If `claude` is on PATH, runs `claude mcp add --scope user gitops-bakery -- <command> <args…>` (removing an existing entry first).
    3. Otherwise logs `Claude Code not found. Register later with: claude mcp add --scope user gitops-bakery -- …` and still succeeds.
  - `removeClaudeIntegration(): Promise<void>`
- `SKILL.md` has frontmatter `name: gitops-bakery` and a description that triggers on GitOps or app-deploy requests in this lab. The body covers:
  - URLs and ports;
  - in-cluster addresses;
  - "use `bakery_create_app` instead of hand-creating repos";
  - the trap table, in 9 short lines;
  - debugging via `bakery_app_status`, then `kubectl -n app-<name>`.

- [ ] **Step 1: Write the failing tests.**

```ts
// tools: names are exactly the four; bakery_create_app rejects {name:"Bad!"} via zod before any deps call
test("tool outputs never contain secret values") // stub deps; run every handler; for each value in secrets, expect(text).not.toContain(value)
// claude: with PATH lacking `claude`, the claude step resolves and the log contains "claude mcp add --scope user gitops-bakery"
// mcpCommand from a checkout → command "node" and args[0] ends with "dist/cli.js"
```

- [ ] **Step 2: Run the tests and see them fail.** → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the tests and see them pass.** `npm test` → pass. Then check the stdio server by hand: `printf '{"jsonrpc":"2.0","id":1,"method":"initialize",...}\n{"jsonrpc":"2.0","id":2,"method":"tools/list"}\n' | node dist/cli.js mcp` lists the 4 tools.
- [ ] **Step 5: Commit.** `feat: add MCP server, Claude skill and integration`.

### Task 11: End-to-end install on a clean Docker

**Files:**
- Create: `test/e2e/install.e2e.sh`, `test/e2e/mcp-client.mjs` (a small MCP client using the SDK `Client` over stdio)
- Modify: `context-notes.md` (timings, memory, raw errors), `checklist.md`

- [ ] **Step 1: Stop and ask the user.** `ml-k8s` occupies 30001–30003 and about 8 GiB. Ask whether to delete it (`kind delete cluster --name ml-k8s`) or stop its node containers. Do nothing until they answer.
- [ ] **Step 2: Write `install.e2e.sh`.** It runs `set -euo pipefail` and records `date +%s` around each phase.
  1. `node dist/cli.js install`
  2. Assert that `kubectl get pods -A` has no pod outside Running or Completed, and that `kubectl -n argocd get applications` shows all Synced/Healthy.
  3. Run `node dist/cli.js install` again, and assert the output contains `(skipped)` for every step.
  4. Run `node test/e2e/mcp-client.mjs create hello`. Poll `bakery_app_status` until the pipeline succeeds, then check that `curl -fsS <url>` returns `"app":"hello"`.
  5. Commit a change to `apps/hello` through the API. Time two intervals:
     - from the CI tag commit to the new version answering, which must be under 60 s;
     - from the source commit to the new version answering, which is only recorded.
  6. Assert `curl -s -o /dev/null -w '%{http_code}' http://localhost/users/sign_in` returns `200`, with no sudo involved.
  7. Run `node dist/cli.js uninstall --yes`. Then assert that `kind get clusters` has no `gitops-bakery`, that `claude mcp list` has no `gitops-bakery`, and that `~/.claude/skills/gitops-bakery` is absent.
- [ ] **Step 3: Run it.** `bash test/e2e/install.e2e.sh 2>&1 | tee .superpowers/e2e.log` → exits 0. On failure, use superpowers:systematic-debugging. Read the step's raw error, fix the code with a unit test where one fits, and rerun from `install` (idempotency is part of the test).
- [ ] **Step 4: Record and commit.** Record the measured times, the `docker stats` memory per node and every trap hit in `context-notes.md`. Commit as `test: add end-to-end install script`.

### Task 12: Docs and publishing

**Files:**
- Create: `README.md` (English), `README.ko.md` (Korean), `docs/traps.md`, `docs/mcp-tools.md`, `docs/architecture.md`

- [ ] **Step 1: Write the docs.**
  - Each README has these sections:
    - one-line pitch;
    - quick start (`npx github:victor-jo/gitops-bakery#v0.1.0 install`);
    - requirements (macOS arm64, OrbStack, 10 GiB, kind/helm/kubectl/git);
    - what gets installed (ports table);
    - the first prompt to try;
    - the MCP tools table;
    - uninstall;
    - roadmap;
    - license.
  - `docs/traps.md` holds the 9-trap table, with the raw error lines taken from `ml-kind-k8s/context-notes.md`.
- [ ] **Step 2: Verify the docs.** Check that every command in the READMEs matches the CLI's `--help`, by running `node dist/cli.js --help` and comparing. Check that no doc contains a real secret, by grepping for each value in the local `secrets.json`.
- [ ] **Step 3: Commit.** `docs: add README (en, ko) and reference docs`. Tag `v0.1.0` locally.
- [ ] **Step 4: Stop and ask the user before publishing.** Then run `gh repo create victor-jo/gitops-bakery --public --source . --push` and `git push origin v0.1.0`.
- [ ] **Step 5: Verify from a clean checkout.** In a temp dir, `npx -y github:victor-jo/gitops-bakery#v0.1.0 doctor` runs and prints the preflight report.
