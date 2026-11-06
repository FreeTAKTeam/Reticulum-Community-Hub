# Consistent RCH Hub Display Name Implementation Plan

**Intent:** Fix issue #294 so the operator's saved hub name reaches the RCH LXMF service identity.
**Current Behavior:** Setup saves `hub_name` and `[hub] name`; startup, config apply and app-info independently read `display_name`; reload and rollback do not update announcements.
**Expected Outcome:** Setup, supported config renames, restart, reload, rollback and diagnostics agree on one name, without changing identity keys or destination hashes.
**Target-Perspective Output:** An operator sees the same name in setup status, app-info and a fresh RCH service announce; failed publication is visible and can be retried with ReloadConfig.
**Truth Owner:** The server owns persisted `rch_settings.hub_name`; INI name fields are compatibility mirrors and the daemon's own identity is separate.
**Contract Boundary:** Authenticated setup/config/control HTTP routes -> persisted name -> existing LXMF SDK identity update/announce.
**Cutover:** At startup/reload, resolve saved nonempty `hub_name`, then `[hub] name`, then `[hub] display_name`, then `RCH`; synchronize legacy mirrors. A config save may explicitly rename through either alias; contradictory edits are rejected.
**Displaced Path:** Independent display-name reads and synthesized app-info names are replaced by the shared server resolver; no daemon fallback overrides the RCH name.
**Value Density:** Reuse SetupFiles for recoverable file installation and the existing identity-update API/error diagnostic. Add no dependencies or new rename endpoint.
**Acceptance Evidence:** HTTP/persistence regressions with conflicting legacy settings, restart/upgrade-shaped fixtures, setup/save/reload/rollback, SDK announce request capture and key/destination checks; isolated real-daemon evidence if a matching executable is available. Columba/Ratspeak require actual connected clients and are reported unproven if unavailable.
**Evidence Lane:** Automated request/response and persisted artifacts plus bounded isolated runtime verification; no production deployment.
**Kill Criteria:** No remaining independent RCH name resolver at setup/startup/app-info/config apply/reload; no replacement identity generation during rename.
**Architecture Slice:** `crates/r3akt-rch-server/src/{hub_name.rs,first_run_setup.rs,lib.rs,main.rs,topic_diagnostics.rs}` and focused tests, with README contract documentation.
**Plan Review Gate:** Requires PRE review before execution.

## Tasks

PRE review resolved: compare submitted aliases with their current file values. One changed alias wins; two equal changes win; competing changes reject; omitted or unchanged aliases retain canonical hub_name. Rollback uses backup name, then display_name, retaining canonical when neither exists. The setup mutex covers selection, recoverable file/SQLite installation, SDK publication and diagnostic recording inside one blocking worker. Installation failures restore the prior file and do not publish. SDK failures preserve the desired name; setup returns successful enrollment with publication pending, while save/reload/rollback return a publication failure. Clear the publication diagnostic only after a successful announce. Exercise failure and concurrent-save behavior.

1. **Main agent:** Add a shared name resolver/reconciler in `hub_name.rs`; route startup, setup status and app-info through it. Reuse existing SQLite helpers and SetupFiles; serialize name mutations with the existing setup lock. Keep identity path and key creation rules unchanged. Verify precedence, validation, recoverable persistence and startup registration with deliberately conflicting names. No parallel writes.
2. **Main agent:** Share the existing announce update implementation across setup, Config save, ReloadConfig and hub rollback. Config saves accept a changed legacy alias, synchronize mirrors and persist the canonical name; ambiguous edits fail before writes. Persisted rename failures return publication errors/diagnostics; setup must distinguish successful credential enrollment from pending publication. Keep Reticulum config rollback behavior separate. Verify HTTP flows, SDK requests, unchanged identity material, and failed-publication retry. Depends on task 1; no parallel writes.
3. **Main agent:** Document precedence, supported rename/retry, daemon-name separation and upgrade behavior in README. Run fmt, workspace clippy and tests using the locked dependencies; add bounded runtime verification where available. Record exact acceptance limits in EVIDENCE.md. Depends on tasks 1–2.
4. **Read-only reviewers:** PRE plan review, then POST correctness/maintainability/evidence review. Main agent fixes material findings. Tests/diffs alone do not prove client display behavior.

## Non-goals and risks

Do not change the frontend, Python branch, daemon's own name, SDK contract, identity files, packaging, live deployment or release version. Existing clients may cache the previous name until receiving a new announce. A network failure after persistence leaves the desired name saved and publication pending; startup or ReloadConfig retries it. Direct file edits after migration do not override the saved name; use PUT /Config for supported renames.

## Execution status

Tasks 1–3 are implemented and validated; PRE, POST and evidence reviews passed.
The workspace passed 756 tests with two intentional live/performance skips using
four test threads and a disk-backed temporary directory. Formatting, Clippy and
real remote setup/rename/restart announces passed. See [EVIDENCE.md](EVIDENCE.md)
for artifacts, environment-sensitive default test failures and remaining actual
Columba/Ratspeak and installed-package upgrade acceptance.
