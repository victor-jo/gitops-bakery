# Context notes — gitops-bakery

Decisions and raw errors, appended as the work goes. The design lives in `docs/superpowers/specs/2026-10-20-gitops-bakery-design.md`.

- **2026-10-20 cluster name.** The user asked for a random cluster name, like Docker's random container names. It is `<adjective>-<bread>`, kept in `state.json`.
- **2026-10-20 old lab removed.** The hand-built `ml-k8s` cluster was deleted (user approved) to free ports 30001–30003 and about 8 GiB.
- **Dependency pins.** commander 14 (15 needs Node ≥ 22.12), vitest 4 (5 needs Node ≥ 22.12), TypeScript 5.9 (7.x is the new native compiler, not adopted yet), so Node ≥ 20 holds.
- **Trap: port 80 looked busy.** `doctor` said `Port 80 on 127.0.0.1 is already in use` while nothing listened (`curl` → 000). On macOS an unprivileged `listen(80, "127.0.0.1")` fails with `EACCES`, not `EADDRINUSE`. Docker (OrbStack) can still publish the port. Only `EADDRINUSE` now counts as busy.
- **Trap: amd64 probe image.** `kubectl run --image=amd64/alpine:3.22` failed with `failed to pull and unpack image "docker.io/amd64/alpine:3.22": no match for platform in manifest: not found`. A tag resolves to an image index, and arm64 containerd only takes an index entry for its own platform. Harbor's images are plain `application/vnd.docker.distribution.manifest.v2+json` manifests, which are pulled as-is and run under Rosetta. The probe now pins `alpine@sha256:3e9b4b…` (the linux/amd64 manifest of alpine:3.22) and prints `x86_64`.
- **First live run.** The cluster got the random name `golden-danish`. The first `install` failed on the probe; the second skipped preflight and finished the cluster step. That is resume-after-failure working on a real cluster.
- **Task 4 live.** Harbor and Argo CD installed on `golden-danish` in one run. `robot$apps+ci` authenticates against `/api/v2.0/projects/apps/repositories` (200). jobservice restarted while the database came up, as in the original lab.
- **Task 5 live.** CNPG, Valkey and Garage installed. Secret key for object storage is `config` (as in the original values and GitLab docs), not `connection` as the plan said.
- **Trap: Garage buckets before layout.** Listing buckets to skip existing ones failed with `ListBuckets returned InternalError (500): Internal error: Layout not ready`. Before a layout is applied, `garage layout show` prints `Current cluster layout version: 0`. The step now applies the layout first, then lists buckets and checks the key. Rerunning the Garage step on a finished cluster succeeds with nothing to do.
- **Task 6 live.** GitLab 19.5 came up and answered `http://localhost/-/readiness` and `/users/sign_in` (200) **without sudo**. Host port 80 goes through the kind mapping to NodePort 30080 on a `gitlab-host` Service. The chart has no setting to pin the webservice NodePort, so the installer copies the `gitlab-webservice-default` selector onto a Service it owns. The root API token is minted by `gitlab-rails runner` in the toolbox with `set_token`, then checked with `GET /api/v4/user`.
- **Task 7 live.** An instance runner `gitops-bakery` is created with `POST /api/v4/user/runners` (a `glrt-` token in Secret `gitlab-runner/gitlab-runner-token`). It came online on the first try.
- **Task 8 live.** `devops/platform` and `devops/service` were seeded through the API. `platform-root`, `service-root` and `monitoring` reached Synced/Healthy, and Grafana answers on 30004.
- **Fast-sync spike (webhook does not work).**
  - What was done: enabled `allow_local_requests_from_web_hooks_and_services`, added a hook on `devops/platform` to `http://argocd-server.argocd.svc.cluster.local/api/webhook`, then committed.
  - Argo CD logged `Received push event repo: http://localhost/devops/platform, revision: main, touchedHead: true` and `Webhook handler completed in 1.264911ms`.
  - It refreshed nothing: `platform-root` `reconciledAt` stayed `2026-10-20T07:38:52Z` for 22 s. The payload URL (`http://localhost/...`) never matches the in-cluster `repoURL`s.
  - Decision: `ci-refresh` mode. The spike hook, file and setting were removed afterwards.
- **ci account.**
  - `accounts.ci: apiKey` with `p, role:ci, applications, get, */*, allow`.
  - Its token can `GET …?refresh=normal` (200).
  - It cannot delete (`permission denied: applications, delete, default/monitoring, sub: ci`, 403) or sync (403).
