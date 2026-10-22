# MCP tools

The server runs on stdio (`gitops-bakery mcp`). Install registers it with Claude Code at user scope as `gitops-bakery`.

## `bakery_status`

No input. Returns:
- cluster name and reachability;
- pod readiness per namespace;
- the in-cluster registry (`<cluster>-control-plane:30001`) and GitLab URL;
- host URLs and usernames;
- created apps with their URLs;
- the path of the secrets file.

## `bakery_create_app`

| Input | |
|---|---|
| `name` | `^[a-z]([a-z0-9-]{0,28}[a-z0-9])?$`; `monitoring`, `platform-root` and `service-root` are reserved |
| `template` | `fastapi` (default) |

In order, it:
1. Creates `apps/<name>-manifests` with a Deployment, a NodePort Service, a ServiceMonitor and a kustomization.
2. Creates a project token on that repo for CI.
3. Creates `apps/<name>` with raw CI variables `HARBOR_USER`, `HARBOR_PASSWORD`, `MANIFEST_TOKEN` and `ARGOCD_TOKEN`.
4. Pushes the template, which starts the first pipeline.
5. Commits `apps/<name>.yaml` to `devops/service`.
6. Refreshes `service-root`.

It refuses a name whose GitLab project already exists. If a later step fails, it removes only what this call created, so a project that existed before is never touched. Returns `url`, `pipelineUrl`, `repo` and `manifestsRepo`.

## `bakery_app_status`

| Input | |
|---|---|
| `name` | an existing app |

Returns:
- the URL;
- the latest pipeline (status, link, jobs);
- the Harbor tags;
- the Argo CD sync and health.

## `bakery_delete_app`

| Input | |
|---|---|
| `name` | an existing app |

Removes `devops/service/apps/<name>.yaml`. Argo CD then cascade-deletes the workload through the Application's finalizer. The tool waits until the Application is gone and deletes namespace `app-<name>`. Then it removes both GitLab repos (permanently) and the Harbor repository. The app's port is released last, so an immediate re-create cannot collide with the old Service.

## Secrets

No tool returns a password or token. A unit test checks every tool's output against every stored secret value.
