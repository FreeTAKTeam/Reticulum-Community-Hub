# Goal: Solid RCH Release

Use Krypton Execution to execute `docs/goals/solid-rch-release/PLAN.md` for the user's request to release a solid RCH version, search for bugs and fix them autonomously, using the LXMF-rs Rust engineering principles for refactoring and optimization.

- Treat PLAN.md as the source plan; retain the full release outcome, ownership, contract, cutover, evidence and kill criteria.
- Preserve the prior LXMF0.12.0 upgrade, unrelated local work and the dirty sibling LXMF-rs checkout.
- Fix confirmed security, durability and runtime defects without duplicate authoritative paths or broad speculative rewrites.
- Capture operator-facing API, persisted-record, browser, real Reticulum runtime and packaged-artifact evidence; passing tests alone do not establish release readiness.
- Keep unperformed external/platform acceptance explicit, and say `implemented but unproven` for behavior without evidence.
- Review and reconcile the final diff against current upstream before any release approval or publication.

Completion: all seven approved local candidate tasks and independent final reviews
passed on 2026-09-30. The locally audited `v3.0.0-preview.11` candidate uses LXMF-rs
`v0.12.0` on current main `188e54f`. The [stabilization report](../../stabilization-v3.0.0-preview.11.md)
records exact acceptance and limits. Native window, hosted/multi-platform/external
acceptance and publication remain separately unperformed; no stable or public
release claim is made.
