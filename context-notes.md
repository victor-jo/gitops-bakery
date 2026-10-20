# Context notes — gitops-bakery

Decisions and raw errors, appended as the work goes. The design lives in `docs/superpowers/specs/2026-10-20-gitops-bakery-design.md`.

- **2026-10-20 cluster name.** The user asked for a random cluster name, like Docker's random container names. It is `<adjective>-<bread>`, kept in `state.json`.
- **2026-10-20 old lab removed.** The hand-built `ml-k8s` cluster was deleted (user approved) to free ports 30001–30003 and about 8 GiB.
- **Dependency pins.** commander 14 (15 needs Node ≥ 22.12), vitest 4 (5 needs Node ≥ 22.12), TypeScript 5.9 (7.x is the new native compiler, not adopted yet), so Node ≥ 20 holds.
