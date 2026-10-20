# The traps

The stack was first built by hand. These are the places where it broke, each with the error as it appeared and what the installer now does about it. The first nine come from the hand-built lab; the rest surfaced while turning it into this installer.

| # | Trap | What it looked like | Handled by |
|---|---|---|---|
| 1 | kind's containerd ignores `certs.d` | containerd has no `config_path`; nodes refuse plain-HTTP Harbor | `containerdConfigPatches` plus `hosts.toml` mounted on every node (`src/kind/config.ts`, `assets/kind/hosts.toml.tmpl`) |
| 2 | Harbor ships amd64 only | official `goharbor/*` images have no arm64 build | preflight probe expects `uname -m` = `x86_64` under Rosetta (`src/steps/cluster.ts`) |
| 3 | GitLab chart 10 bundles no PostgreSQL, Redis or S3 | `helm template` fails without `global.psql.host`, `global.redis.host` and object storage; then the migration fails with `ERROR:  out of shared memory` | CloudNativePG with `max_locks_per_transaction: "256"`, Valkey, and Garage with the multi-arch image `dxflrs/garage` (`src/steps/{cnpg,valkey,garage}.ts`) |
| 4 | GitLab's host cannot carry a port | `URI::InvalidComponentError: bad component(expected host component): [localhost:30000]`, then `bind: permission denied` for an unprivileged port-forward on 127.0.0.1:80 | Host stays `localhost`; kind maps host port 80 (Docker binds it without sudo) to the `gitlab-host` NodePort service (`src/steps/gitlab.ts`) |
| 5 | Runner helper defaults to amd64 | `no match for platform in manifest: not found` | `node_selector kubernetes.io/arch` set to the host arch; seccomp `Unconfined` for rootless BuildKit (`assets/values/gitlab-runner.yaml`) |
| 6 | GitLab expands `$` inside variable values | `unauthorized to access repository: jokes/joke-api, action: push`; Harbor logged `robot+ci` instead of `robot$jokes+ci` | CI variables are always created with `raw: true` (`src/apps/lifecycle.ts`) |
| 7 | `registry.enabled: false` only skips pods | `Faraday::ConnectionFailed: Failed to open TCP connection to gitlab-registry.gitlab.svc:5000 (getaddrinfo: Name or service not known)` on project transfer | `global.registry.enabled: false` too (`assets/values/gitlab.yaml`) |
| 8 | Manifest repos are written by CI as well | `git subtree pull` → `fatal: refusing to merge unrelated histories` | Repos are only touched through the GitLab API; CI runs `git pull --rebase` before pushing |
| 9 | Human clicks vanish on a `rate()` graph | about 1 req/s shows as a tiny bump that is gone a minute later | Dashboard uses a cumulative stat (unit `none`) and `increase(...[1m])` |
| 10 | GitLab webhooks never refresh Argo CD here | Argo CD logs `Received push event repo: http://localhost/devops/platform` and refreshes nothing | CI calls the Argo CD refresh API with a token that can only `get` applications |
| 11 | Argo CD answers 403 for apps it has not created yet | `wget: server returned error: HTTP/1.1 403 Forbidden` in the first deploy job | `bakery_create_app` refreshes `service-root` immediately; the CI refresh is best effort |
| 12 | GitLab deletes group projects lazily | `405 {"message":"Non GET methods are not allowed for moved projects"}` | Delete by id, then `permanently_remove=true` with the renamed path |
| 13 | `kubectl run -i` loses the output of fast pods | empty output, or `couldn't attach to pod … falling back to streaming logs` | The emulation probe runs detached and reads logs after `Succeeded` |
| 14 | macOS refuses unprivileged binds below 1024 | preflight reported port 80 as busy (`EACCES`) while nothing listened | Only `EADDRINUSE` counts as busy |
| 15 | A multi-arch tag cannot test amd64 emulation | `amd64/alpine:3.22`: `no match for platform in manifest` on arm64 nodes | The probe pins the linux/amd64 manifest by digest, like Harbor's single-arch images |
| 16 | Garage buckets cannot be listed before a layout exists | `ListBuckets returned InternalError (500): Internal error: Layout not ready` | Apply the layout first, then check buckets and keys |
