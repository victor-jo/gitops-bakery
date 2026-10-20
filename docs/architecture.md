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
