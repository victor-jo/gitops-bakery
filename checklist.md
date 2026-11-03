# Checklist — gitops-bakery v0.1

Plan: `docs/superpowers/plans/2026-10-20-gitops-bakery-v0.1.md`

- [x] 1. Scaffold and core libraries
- [x] 2. kind config, preflight, cluster step
- [x] 3. Step runner and CLI
- [x] 4. Harbor and Argo CD
- [x] 5. CloudNativePG, Valkey, Garage
- [x] 6. GitLab and the GitLab client
- [x] 7. GitLab Runner
- [x] 8. GitOps bootstrap, monitoring, fast sync
- [x] 9. App lifecycle and FastAPI template
- [x] 10. MCP server, skill, Claude Code integration
- [x] 11. End-to-end install
- [x] 12. Docs (publishing waits for the user)

# v0.1.1 — deferred review fixes (plan: docs/superpowers/plans/2026-10-20-v0.1.1-fixes.md)

- [x] 1. Branch and bookkeeping
- [x] 2. Token never in argv/errors; quoted claude command (items 1, 5)
- [x] 3. App lifecycle: refuse existing repos, safe delete, docs (items 2, 6, 9)
- [x] 4. Resume robustness: Garage cache, helm pending (items 3, 4)
- [x] 5. Uninstall without state, doctor wording (items 7, 8)
- [x] 6. Release: E2E, review, merge, publish (asks first)

# --with-ml — the ML lab as an install option (plan: docs/superpowers/plans/2026-10-29-with-ml.md)

- [x] 1. Platform manifests into `assets/gitops/platform-ml/` with host and GitLab templates; NodePorts in the app range dropped
- [x] 2. Plumbing: `--with-ml`, `state.options`, `state.ml.hosts`, `installSteps`, ML preflight
- [x] 3. Steps: storage, gateways, platform, seed Jobs, KFP image
- [x] 4. `labs/ml` exercises with upstream fetch and patch (no upstream code in the repo)
- [x] 5. Unit tests (`test/unit/ml.test.ts`) and `WITH_ML=1` E2E mode
- [x] 6. Docs: README (en, ko), architecture, traps 17–31
- [x] 7. Live upgrade on `crusty-focaccia`: all ML apps at the new head, 5 names answer, 30,162 online keys, arm64 image pushed, KFP run SUCCEEDED, local runner 30,162 rows
- [x] 8. Fresh install with --with-ml on `honeyed-bagel`: 1001 s, all apps healthy, new gateway IPs, 30,162 keys, 10.9 GiB
- [ ] 9. Push branch and open the PR (ask first)

# Evidently — drift monitoring on the ML layer (plan: ~/.claude/plans/https-github-com-evidentlyai-evidently-sleepy-summit.md)

- [x] 1. Evidently UI app in `devops/platform`: namespace `evidently`, PVC workspace, `evidently-service-internal:8000`, sslip.io Ingress
- [x] 2. Installer: `evidently` gateway name, `ml-drift-image` step, status/MCP/env.sh show the name
- [x] 3. Notebook lineage fix (`patch_notebook.py`) and kfp read grant on `mlflow-datasets`
- [x] 4. `labs/ml/drift`: `income-drift-detection` pipeline, `run_local.sh`, `pf.sh`
- [x] 5. Unit tests (118 pass) and docs (READMEs, architecture, traps 33–35, labs/ml section 6)
- [x] 6. Live upgrade on `honeyed-bagel`: install, retrain, champion, drift on Mac and in KFP
- [ ] 7. Push branch and open the PR (ask first)

# BentoML drift service on Docker (book 6.3; decisions in context-notes.md)

- [x] 1. `labs/ml/serving`: BentoML 1.4.39 service with a 100-row drift window, the champion baked in at build time
- [x] 2. build.sh (import model, bentoml build, containerize), run.sh (docker run on the kind network), send_requests.py
- [x] 3. Live check: 200 requests → reports in Evidently project `income-classifier-realtime`
- [x] 4. Docs (labs/ml README, traps) and tests
