# Python Parity Plus Rust Release Capability Report

Generated: 2026-05-13T08:21:13.0613693-03:00

## Baselines

- Python baseline branch: `rch-python`
- Python baseline commit: `a520574ecbc243841a1a215b616b6792452de2a1`
- Rust branch: `rust-next`
- Rust commit: `a897761046072c9b2f07d0afb6b6911077e31e3b`
- LXMF-rs sibling baseline: `v0.4.0`
  (`2393131d5729f50cbe74a7a9bfeff11d2d5d499e`), updated 2026-06-14
- LXMF-rs resolved package tuple: `lxmf-wire` `0.2.0`, `lxmf-sdk` `0.2.1`,
  `reticulum-rs-rpc` `0.3.0`, `lxmf-reference` `0.1.0`
- Contract matrix: `docs/release-contract-matrix.json`
- Rust OpenAPI probe: `http://127.0.0.1:18180`
- Python OpenAPI probe: `http://127.0.0.1:18181`

## Decision Model

- `must-match-python`: Python public behavior that Rust must preserve.
- `rust-additive-required`: Rust release capability that is mandatory even when Python lacks it.
- `intentional-difference`: Documented architecture difference with equivalent or improved public behavior.

## Contract Summary

| Classification | Contracts | HTTP routes |
| --- | ---: | ---: |
| must-match-python | 4 | 166 |
| rust-additive-required | 7 | 0 |
| intentional-difference | 2 | 0 |

## Python-Compatible Contracts

- `python-northbound-http-routes` (http-route): Python northbound HTTP and WebSocket route inventory exposed by Rust OpenAPI.
- `python-lxmf-legacy-command-surface` (lxmf-legacy-command): Legacy/plugin command names, aliases, admin commands, telemetry request, and attachment commands documented by Python RCH.
- `python-mission-checklist-command-surface` (field-command-envelope): Mission-sync and checklist command envelope lifecycle, capabilities, result/rejection shape, and persisted state.
- `python-tak-compatible-behavior` (tak-behavior): TAK CoT XML/protobuf profile selection, keepalive, reconnect, inbound marker mapping, chat/location relay, and compatible config fields.

## Rust Additive Required Capabilities

- `rust-additive-rem-compatibility` (rem-compatibility): REM connected/autonomous/semi-autonomous behavior, peer registry, EAM command fanout, checklist command fanout, replay, markdown fallback, and duplicate suppression.
- `rust-additive-reticulumd-runtime` (reticulum-runtime): LXMF-rs reticulumd RPC/event-cursor runtime for direct send, topic fanout, receipts, retries, inbound relay, attachments, telemetry, announces, and diagnostics.
- `rust-additive-runtime-diagnostics` (diagnostics): Richer /diagnostics/runtime inventory for persistence, workers, reticulumd RPC/process state, queues, counters, receipts, and schema version.
- `rust-additive-python-install-import` (migration): Install-over-Python migration path for Python config, identity, Reticulum identity, SQLite DB, telemetry DB, files, images, LXMF data, and first-start prompt behavior.
- `rust-additive-standalone-tak-service` (tak-service): Standalone r3akt-tak-service boundary with sidecar packaging, service diagnostics, queue drain, retry, and failure reporting.
- `rust-additive-tauri-sidecars` (packaging): Tauri desktop sidecar packaging for Rust server and standalone TAK service without reintroducing Electron on rust-next.
- `rust-additive-release-gates` (release-gate): Rust release gate runner, local/external Reticulum gates, coverage/report evidence, and workspace checks.

## Intentional Differences

- `intentional-rust-reticulum-runtime-boundary` (architecture): Python embedded RNS/LXMF runtime is replaced by managed LXMF-rs reticulumd RPC/event-cursor runtime; public delivery and route outcomes must remain Python-compatible.
- `intentional-rust-tak-service-boundary` (architecture): TAK socket lifecycle is owned by standalone r3akt-tak-service instead of the Rust HTTP server; northbound behavior and CoT semantics remain compatible.

## HTTP Route Probe Results

| Method | Path | Rust OpenAPI | Python OpenAPI |
| --- | --- | --- | --- |
| `POST` | `/Chat/Attachment` | pass | pass |
| `POST` | `/Chat/Message` | pass | pass |
| `GET` | `/Chat/Messages` | pass | pass |
| `GET` | `/Client` | pass | pass |
| `POST` | `/Client/{identity}/Ban` | pass | pass |
| `POST` | `/Client/{identity}/Blackhole` | pass | pass |
| `POST` | `/Client/{identity}/Unban` | pass | pass |
| `GET` | `/Command/DumpRouting` | pass | pass |
| `POST` | `/Command/FlushTelemetry` | pass | pass |
| `POST` | `/Command/ReloadConfig` | pass | pass |
| `GET` | `/Config` | pass | pass |
| `PUT` | `/Config` | pass | pass |
| `POST` | `/Config/Rollback` | pass | pass |
| `POST` | `/Config/Validate` | pass | pass |
| `POST` | `/Control/Announce` | pass | missing-path |
| `POST` | `/Control/Start` | pass | missing-path |
| `GET` | `/Control/Status` | pass | missing-path |
| `POST` | `/Control/Stop` | pass | missing-path |
| `POST` | `/Control/Sync` | pass | missing-path |
| `GET` | `/Diagnostics/Runtime` | pass | pass |
| `GET` | `/Events` | pass | pass |
| `GET` | `/Examples` | pass | pass |
| `GET` | `/File` | pass | pass |
| `DELETE` | `/File/{file_id}` | pass | pass |
| `GET` | `/File/{file_id}` | pass | pass |
| `PATCH` | `/File/{file_id}` | pass | pass |
| `GET` | `/File/{file_id}/raw` | pass | pass |
| `GET` | `/Help` | pass | pass |
| `GET` | `/Identities` | pass | pass |
| `GET` | `/Image` | pass | pass |
| `DELETE` | `/Image/{file_id}` | pass | pass |
| `GET` | `/Image/{file_id}` | pass | pass |
| `PATCH` | `/Image/{file_id}` | pass | pass |
| `GET` | `/Image/{file_id}/raw` | pass | pass |
| `POST` | `/Message` | pass | pass |
| `POST` | `/RCH` | pass | pass |
| `PUT` | `/RCH` | pass | pass |
| `POST` | `/RTH` | pass | pass |
| `PUT` | `/RTH` | pass | pass |
| `GET` | `/Reticulum/Config` | pass | pass |
| `PUT` | `/Reticulum/Config` | pass | pass |
| `POST` | `/Reticulum/Config/Rollback` | pass | pass |
| `POST` | `/Reticulum/Config/Validate` | pass | pass |
| `GET` | `/Reticulum/Discovery` | pass | pass |
| `GET` | `/Reticulum/Interfaces/Capabilities` | pass | pass |
| `GET` | `/Status` | pass | pass |
| `DELETE` | `/Subscriber` | pass | pass |
| `GET` | `/Subscriber` | pass | pass |
| `PATCH` | `/Subscriber` | pass | pass |
| `POST` | `/Subscriber` | pass | pass |
| `POST` | `/Subscriber/Add` | pass | pass |
| `GET` | `/Subscriber/{subscriber_id}` | pass | pass |
| `GET` | `/Telemetry` | pass | pass |
| `DELETE` | `/Topic` | pass | pass |
| `GET` | `/Topic` | pass | pass |
| `PATCH` | `/Topic` | pass | pass |
| `POST` | `/Topic` | pass | pass |
| `POST` | `/Topic/Associate` | pass | pass |
| `POST` | `/Topic/Subscribe` | pass | pass |
| `GET` | `/Topic/{topic_id}` | pass | pass |
| `GET` | `/api/EmergencyActionMessage` | pass | pass |
| `POST` | `/api/EmergencyActionMessage` | pass | pass |
| `GET` | `/api/EmergencyActionMessage/latest/{team_member_uid}` | pass | pass |
| `GET` | `/api/EmergencyActionMessage/team/{team_uid}/summary` | pass | pass |
| `DELETE` | `/api/EmergencyActionMessage/{callsign}` | pass | pass |
| `GET` | `/api/EmergencyActionMessage/{callsign}` | pass | pass |
| `PUT` | `/api/EmergencyActionMessage/{callsign}` | pass | pass |
| `GET` | `/api/markers` | pass | pass |
| `POST` | `/api/markers` | pass | pass |
| `GET` | `/api/markers/symbols` | pass | pass |
| `DELETE` | `/api/markers/{object_destination_hash}` | pass | pass |
| `PATCH` | `/api/markers/{object_destination_hash}` | pass | pass |
| `PATCH` | `/api/markers/{object_destination_hash}/position` | pass | pass |
| `GET` | `/api/r3akt/assets` | pass | pass |
| `POST` | `/api/r3akt/assets` | pass | pass |
| `DELETE` | `/api/r3akt/assets/{asset_uid}` | pass | pass |
| `GET` | `/api/r3akt/assets/{asset_uid}` | pass | pass |
| `GET` | `/api/r3akt/assignments` | pass | pass |
| `POST` | `/api/r3akt/assignments` | pass | pass |
| `PUT` | `/api/r3akt/assignments/{assignment_uid}/assets` | pass | pass |
| `DELETE` | `/api/r3akt/assignments/{assignment_uid}/assets/{asset_uid}` | pass | pass |
| `PUT` | `/api/r3akt/assignments/{assignment_uid}/assets/{asset_uid}` | pass | pass |
| `GET` | `/api/r3akt/capabilities/{identity}` | pass | pass |
| `DELETE` | `/api/r3akt/capabilities/{identity}/{capability}` | pass | pass |
| `PUT` | `/api/r3akt/capabilities/{identity}/{capability}` | pass | pass |
| `GET` | `/api/r3akt/events` | pass | pass |
| `GET` | `/api/r3akt/log-entries` | pass | pass |
| `POST` | `/api/r3akt/log-entries` | pass | pass |
| `GET` | `/api/r3akt/mission-changes` | pass | pass |
| `POST` | `/api/r3akt/mission-changes` | pass | pass |
| `GET` | `/api/r3akt/missions` | pass | pass |
| `POST` | `/api/r3akt/missions` | pass | pass |
| `DELETE` | `/api/r3akt/missions/{mission_uid}` | pass | pass |
| `GET` | `/api/r3akt/missions/{mission_uid}` | pass | pass |
| `PATCH` | `/api/r3akt/missions/{mission_uid}` | pass | pass |
| `GET` | `/api/r3akt/missions/{mission_uid}/markers` | pass | pass |
| `DELETE` | `/api/r3akt/missions/{mission_uid}/markers/{marker_id}` | pass | pass |
| `PUT` | `/api/r3akt/missions/{mission_uid}/markers/{marker_id}` | pass | pass |
| `PUT` | `/api/r3akt/missions/{mission_uid}/parent` | pass | pass |
| `GET` | `/api/r3akt/missions/{mission_uid}/rde` | pass | pass |
| `PUT` | `/api/r3akt/missions/{mission_uid}/rde` | pass | pass |
| `GET` | `/api/r3akt/missions/{mission_uid}/zones` | pass | pass |
| `DELETE` | `/api/r3akt/missions/{mission_uid}/zones/{zone_id}` | pass | pass |
| `PUT` | `/api/r3akt/missions/{mission_uid}/zones/{zone_id}` | pass | pass |
| `GET` | `/api/r3akt/rights/definitions` | pass | pass |
| `DELETE` | `/api/r3akt/rights/grants` | pass | pass |
| `GET` | `/api/r3akt/rights/grants` | pass | pass |
| `PUT` | `/api/r3akt/rights/grants` | pass | pass |
| `DELETE` | `/api/r3akt/rights/mission-access` | pass | pass |
| `GET` | `/api/r3akt/rights/mission-access` | pass | pass |
| `PUT` | `/api/r3akt/rights/mission-access` | pass | pass |
| `GET` | `/api/r3akt/rights/subjects` | pass | pass |
| `GET` | `/api/r3akt/skills` | pass | pass |
| `POST` | `/api/r3akt/skills` | pass | pass |
| `GET` | `/api/r3akt/snapshots` | pass | pass |
| `GET` | `/api/r3akt/task-skill-requirements` | pass | pass |
| `POST` | `/api/r3akt/task-skill-requirements` | pass | pass |
| `GET` | `/api/r3akt/team-member-skills` | pass | pass |
| `POST` | `/api/r3akt/team-member-skills` | pass | pass |
| `GET` | `/api/r3akt/team-members` | pass | pass |
| `POST` | `/api/r3akt/team-members` | pass | pass |
| `DELETE` | `/api/r3akt/team-members/{team_member_uid}` | pass | pass |
| `GET` | `/api/r3akt/team-members/{team_member_uid}` | pass | pass |
| `GET` | `/api/r3akt/team-members/{team_member_uid}/clients` | pass | pass |
| `DELETE` | `/api/r3akt/team-members/{team_member_uid}/clients/{client_identity}` | pass | pass |
| `PUT` | `/api/r3akt/team-members/{team_member_uid}/clients/{client_identity}` | pass | pass |
| `GET` | `/api/r3akt/teams` | pass | pass |
| `POST` | `/api/r3akt/teams` | pass | pass |
| `DELETE` | `/api/r3akt/teams/{team_uid}` | pass | pass |
| `GET` | `/api/r3akt/teams/{team_uid}` | pass | pass |
| `GET` | `/api/r3akt/teams/{team_uid}/missions` | pass | pass |
| `DELETE` | `/api/r3akt/teams/{team_uid}/missions/{mission_uid}` | pass | pass |
| `PUT` | `/api/r3akt/teams/{team_uid}/missions/{mission_uid}` | pass | pass |
| `GET` | `/api/rem/peers` | pass | pass |
| `GET` | `/api/v1/app/info` | pass | pass |
| `GET` | `/api/v1/auth/validate` | pass | pass |
| `GET` | `/api/zones` | pass | pass |
| `POST` | `/api/zones` | pass | pass |
| `DELETE` | `/api/zones/{zone_id}` | pass | pass |
| `PATCH` | `/api/zones/{zone_id}` | pass | pass |
| `GET` | `/checklists` | pass | pass |
| `POST` | `/checklists` | pass | pass |
| `POST` | `/checklists/import/csv` | pass | pass |
| `POST` | `/checklists/offline` | pass | pass |
| `GET` | `/checklists/templates` | pass | pass |
| `POST` | `/checklists/templates` | pass | pass |
| `DELETE` | `/checklists/templates/{template_id}` | pass | pass |
| `GET` | `/checklists/templates/{template_id}` | pass | pass |
| `PATCH` | `/checklists/templates/{template_id}` | pass | pass |
| `POST` | `/checklists/templates/{template_id}/clone` | pass | pass |
| `DELETE` | `/checklists/{checklist_id}` | pass | pass |
| `GET` | `/checklists/{checklist_id}` | pass | pass |
| `PATCH` | `/checklists/{checklist_id}` | pass | pass |
| `POST` | `/checklists/{checklist_id}/feeds/{feed_id}` | pass | pass |
| `POST` | `/checklists/{checklist_id}/join` | pass | pass |
| `POST` | `/checklists/{checklist_id}/tasks` | pass | pass |
| `DELETE` | `/checklists/{checklist_id}/tasks/{task_id}` | pass | pass |
| `PATCH` | `/checklists/{checklist_id}/tasks/{task_id}/cells/{column_id}` | pass | pass |
| `PATCH` | `/checklists/{checklist_id}/tasks/{task_id}/row-style` | pass | pass |
| `POST` | `/checklists/{checklist_id}/tasks/{task_id}/status` | pass | pass |
| `POST` | `/checklists/{checklist_id}/upload` | pass | pass |
| `GET` | `/diagnostics/runtime` | pass | pass |
| `GET` | `/events/system` | pass | missing-path |
| `GET` | `/messages/stream` | pass | missing-path |
| `GET` | `/openapi.yaml` | pass | missing-path |
| `GET` | `/telemetry/stream` | pass | missing-path |

## Release Decision Inputs

- Rust OpenAPI has no failed route probes for the matrix scope.
- Python OpenAPI route probe failures: 9
- Rust additive capability gates must still be backed by their named evidence commands before final release.
- True Python-visible mismatches must be fixed or explicitly waived; Rust additive failures block release even without Python equivalents.

## Workspace Status

```text
M Cargo.lock
 M crates/r3akt-rch-core/src/lib.rs
 M crates/r3akt-rch-server/Cargo.toml
 M crates/r3akt-rch-server/src/main.rs
 M docs/release-readiness-audit.md
 M docs/rust-transition.md
 M packaging/README.md
?? .coverage
?? .desloppify/
?? .tmp_internal_ws_smoke/
?? .venv/
?? .vscode/
?? RCH_Store/
?? RTH_Store/
?? crates/r3akt-rch-core/src/bin/
?? crates/r3akt-rch-core/src/python_migration.rs
?? crates/r3akt-rch-server/tests/release_contract_matrix.rs
?? dist/
?? docs/architecture/
?? docs/example_telemetry.json
?? docs/release-contract-matrix.json
?? docs/release-parity-report.md
?? docs/telemetry.db
?? electron/
?? reticulum_telemetry_hub/
?? scripts/migrate-python-rch.ps1
?? scripts/python-rust-parity.ps1
?? telemetry.db
?? tests/
?? venv_linux/
```
