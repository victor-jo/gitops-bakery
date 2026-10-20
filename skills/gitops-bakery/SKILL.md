---
name: gitops-bakery
description: Use when the user wants to create, deploy, inspect or delete an app in the local gitops-bakery lab (kind + GitLab + Harbor + Argo CD + Prometheus/Grafana), asks to "deploy with GitOps" on this machine, or asks about the lab's URLs, pipelines, images or sync state.
---

# gitops-bakery lab

A local GitOps lab on a kind cluster. Code lives in GitLab, GitLab Runner builds images with rootless BuildKit and pushes them to Harbor, CI bumps the image tag in a manifests repo, and Argo CD deploys it. Prometheus scrapes every app and Grafana shows request counts.

## Use the MCP tools first

| Want | Tool |
|---|---|
| Lab health, URLs, usernames, registry name, apps | `bakery_status` |
| New app deployed with GitOps | `bakery_create_app` (`name`, `template: "fastapi"`) |
| Pipeline, image tags, sync/health, URL of one app | `bakery_app_status` |
| Remove an app completely | `bakery_delete_app` |

Do not create GitLab repos, CI variables or Argo CD Applications by hand. `bakery_create_app` sets them up correctly, including the traps below. After creating an app, poll `bakery_app_status` until the pipeline is `success` and Argo CD shows `Synced`/`Healthy`, then give the user the URL. The first pipeline takes about a minute.

Passwords are never returned by the tools. They are in `~/.gitops-bakery/secrets.json`; point the user there instead of printing them.

## Addresses

| From | GitLab | Harbor | Argo CD | Grafana |
|---|---|---|---|---|
| The user's browser | http://localhost | http://localhost:30001 | http://localhost:30002 | http://localhost:30004 |
| Pods and CI jobs | http://gitlab-webservice-default.gitlab.svc.cluster.local:8181 | `<cluster>-control-plane:30001` (see `bakery_status`) | http://argocd-server.argocd.svc.cluster.local | — |

Apps get host ports 30010–30019 and run in namespace `app-<name>`.

## Changing an app

Edit files in GitLab project `apps/<name>` (clone `http://localhost/apps/<name>.git` with the root user, or use the GitLab API). A push runs test → build → deploy. Never hand-edit `apps/<name>-manifests`; CI owns its `newTag`. To change Kubernetes objects (replicas, env), edit the manifests repo, then `git pull --rebase` before pushing because CI pushes there too.

## Traps this lab already handles (do not undo them)

1. containerd only trusts the HTTP Harbor through `hosts.toml` mounted on every node.
2. Harbor images are amd64-only and run under Rosetta emulation.
3. GitLab chart 10 has no bundled DB/Redis/S3; CloudNativePG (`max_locks_per_transaction=256`), Valkey and Garage replace them.
4. GitLab's host must be bare `localhost` (port 80); in-cluster clients use the internal URL.
5. Runner jobs pin `kubernetes.io/arch` to the host arch (the helper image defaults to amd64) and use seccomp `Unconfined` for rootless BuildKit.
6. CI variables are `raw`, because GitLab expands the `$` in `robot$apps+ci`.
7. `global.registry.enabled: false`, or GitLab calls a registry that does not exist.
8. Manifest repos are written by CI too; never force-push them.
9. Dashboards use cumulative counts and `increase(...[1m])`, because human clicks vanish on a `rate()` graph.

## Debugging

1. `bakery_app_status` shows which stage failed and has the pipeline link.
2. Pods: `kubectl --context kind-<cluster> -n app-<name> get pods` and `logs`. The cluster name is in `bakery_status`.
3. A Synced app on the old version usually means the deploy job failed; check its log in the pipeline.
