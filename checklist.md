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
- [ ] 3. App lifecycle: refuse existing repos, safe delete, docs (items 2, 6, 9)
- [ ] 4. Resume robustness: Garage cache, helm pending (items 3, 4)
- [ ] 5. Uninstall without state, doctor wording (items 7, 8)
- [ ] 6. Release: E2E, review, merge, publish (asks first)
