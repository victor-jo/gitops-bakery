# Architecture

```
npx gitops-bakery install
  preflight → kind cluster (random name) → Harbor → Argo CD → CloudNativePG → Valkey → Garage
  → GitLab → root token → GitLab Runner → GitOps bootstrap → fast sync → Claude Code
```

Each arrow is an idempotent step (`src/steps/*.ts`). Completed steps are recorded in `~/.gitops-bakery/state.json`, so a rerun skips them and a failure resumes where it stopped.

## Repos inside the lab

```
GitLab
├─ devops/platform    root.yaml, apps/monitoring.yaml, monitoring/values.yaml, monitoring/dashboards/
├─ devops/service     root.yaml, apps/<name>.yaml (one per app)
└─ apps/
   ├─ <name>              source, Dockerfile (test stage), .gitlab-ci.yml
   └─ <name>-manifests    Deployment, Service, ServiceMonitor, kustomization (CI owns newTag)
```

The installer applies `platform-root` and `service-root` by hand. Argo CD creates everything else from git.

## One push, end to end

```
push apps/<name>
  → Runner job pod: BuildKit test stage
  → BuildKit build, push <cluster>-control-plane:30001/apps/<name>:<sha>
  → deploy job: bump newTag in apps/<name>-manifests, git pull --rebase, push
  → deploy job: GET argocd-server/api/v1/applications/<name>?refresh=normal (token "ci", get-only)
  → Argo CD syncs namespace app-<name>; Prometheus scrapes /metrics through the ServiceMonitor
```

## Why CI refreshes Argo CD instead of a webhook

GitLab's host is `localhost`, because its config takes no port and the browser reaches it on port 80. Argo CD's webhook handler matches the push payload's project URL against each Application's `repoURL`. The payload carries `http://localhost/...`, while Argo CD only knows the in-cluster `http://gitlab-webservice-default.gitlab.svc.cluster.local:8181/...`. Nothing matches, so nothing refreshes. This was measured: no refresh after 22 s.

The CI refresh call does match, and it brings the CI-tag-to-live time down to 4–13 s. A failed refresh never fails the job, because Argo CD still polls every 3 minutes.

## Addresses

| From | GitLab | Registry | Argo CD |
|---|---|---|---|
| Host | http://localhost | http://localhost:30001 | http://localhost:30002 |
| Pods and nodes | http://gitlab-webservice-default.gitlab.svc.cluster.local:8181 | `<cluster>-control-plane:30001` (HTTP, trusted through `hosts.toml`) | http://argocd-server.argocd.svc.cluster.local |

## The ML layer (`install --with-ml`)

```text
Mac browser ──> mlflow.<ip>.sslip.io ──> lo0 alias (cloud-provider-kind, sudo) ──> envoy gateway ──> Ingress ──> Service
                 one gateway IP per namespace: mlflow (MLflow, Jupyter), feast, kubeflow, monitoring
```

1. **`ml-preflight`.** Checks for at least 14 GiB of Docker memory and a running `cloud-provider-kind`. It runs as its own step because a lab installed without the flag already has `preflight` marked done.
2. **`ml-storage`.** Creates six Garage buckets and four keys, each key with only its consumer's buckets, plus six Secrets. Secret values stay out of git.
3. **`ml-gateways`.** Waits for each namespace's gateway IP, using a hostless probe Ingress where needed, and stores the sslip.io names in `state.json`.
4. **`ml-platform`.** Renders `assets/gitops/platform-ml/` with those names and commits only the changed files to `devops/platform`, together with the base set. It then waits for `feast-operator`, `mlflow`, `jupyter`, `feast-store`, `kfp` and `monitoring`.
5. **`ml-seed`.** Two Jobs run the Feast feature-server image:
   - `feast/ml-seed-features` uploads the example parquet files, applies both registries and materializes 30,162 users into Valkey db 1;
   - `kubeflow/ml-seed-inference` uploads the scoring input.
6. **`ml-kfp-image`.** Builds `labs/ml/kfp/pipeline/src` for the host architecture and pushes it to Harbor's public `kfp` project. It uses a throwaway Docker config, so the Harbor login never lands in `~/.docker`.

The upstream example code, data and notebook are never copied into this repo. Jobs and scripts fetch them at a pinned commit, and the lab's changes live as patches (`patch_notebook.py`, `labs/ml/kfp/upstream/lab.patch`).

Garage (3900) and Valkey (6379) have no name. They are storage, not UIs. Mac-side Feast or AWS CLI work goes through `labs/ml/feast/pf.sh`.
