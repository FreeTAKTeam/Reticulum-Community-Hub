# Python Parity Plus Rust Release Capability Report

Generated: 2026-06-21T22:30:41.7860979-03:00

## Baselines

- Python baseline branch: `rch-python`
- Python baseline commit: `a520574ecbc243841a1a215b616b6792452de2a1`
- Rust branch: `main`
- Rust commit: `2fc0bb20c6bdce88906049d5408f815702d178dc`
- LXMF-rs sibling commit: `81acffc1409a760aeb9d7b09dc9a76b4be304a59`
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
| must-match-python | 4 | 157 |
| rust-additive-required | 8 | 9 |
| intentional-difference | 2 | 0 |

## Python-Compatible Contracts

- `python-northbound-http-routes` (http-route): Python northbound HTTP and WebSocket route inventory exposed by Rust OpenAPI.
- `python-lxmf-legacy-command-surface` (lxmf-legacy-command): Legacy/plugin command names, aliases, admin commands, telemetry request, and attachment commands documented by Python RCH.
- `python-mission-checklist-command-surface` (field-command-envelope): Mission-sync and checklist command envelope lifecycle, capabilities, result/rejection shape, and persisted state.
- `python-tak-compatible-behavior` (tak-behavior): TAK CoT XML/protobuf profile selection, keepalive, reconnect, inbound marker mapping, chat/location relay, and compatible config fields.

## Rust Additive Required Capabilities

- `rust-additive-http-routes` (http-route): Rust-only operator control, streaming, and OpenAPI convenience routes that Python 2.9.x does not expose but the Rust release must keep.
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

| Classification | Method | Path | Rust OpenAPI | Python OpenAPI |
| --- | --- | --- | --- | --- |
| `must-match-python` | `POST` | `/Chat/Attachment` | pass | pass |
| `must-match-python` | `POST` | `/Chat/Message` | pass | pass |
| `must-match-python` | `GET` | `/Chat/Messages` | pass | pass |
| `must-match-python` | `GET` | `/Client` | pass | pass |
| `must-match-python` | `POST` | `/Client/{identity}/Ban` | pass | pass |
| `must-match-python` | `POST` | `/Client/{identity}/Blackhole` | pass | pass |
| `must-match-python` | `POST` | `/Client/{identity}/Unban` | pass | pass |
| `must-match-python` | `GET` | `/Command/DumpRouting` | pass | pass |
| `must-match-python` | `POST` | `/Command/FlushTelemetry` | pass | pass |
| `must-match-python` | `POST` | `/Command/ReloadConfig` | pass | pass |
| `must-match-python` | `GET` | `/Config` | pass | pass |
| `must-match-python` | `PUT` | `/Config` | pass | pass |
| `must-match-python` | `POST` | `/Config/Rollback` | pass | pass |
| `must-match-python` | `POST` | `/Config/Validate` | pass | pass |
| `must-match-python` | `GET` | `/Diagnostics/Runtime` | pass | pass |
| `must-match-python` | `GET` | `/Events` | pass | pass |
| `must-match-python` | `GET` | `/Examples` | pass | pass |
| `must-match-python` | `GET` | `/File` | pass | pass |
| `must-match-python` | `DELETE` | `/File/{file_id}` | pass | pass |
| `must-match-python` | `GET` | `/File/{file_id}` | pass | pass |
| `must-match-python` | `PATCH` | `/File/{file_id}` | pass | pass |
| `must-match-python` | `GET` | `/File/{file_id}/raw` | pass | pass |
| `must-match-python` | `GET` | `/Help` | pass | pass |
| `must-match-python` | `GET` | `/Identities` | pass | pass |
| `must-match-python` | `GET` | `/Image` | pass | pass |
| `must-match-python` | `DELETE` | `/Image/{file_id}` | pass | pass |
| `must-match-python` | `GET` | `/Image/{file_id}` | pass | pass |
| `must-match-python` | `PATCH` | `/Image/{file_id}` | pass | pass |
| `must-match-python` | `GET` | `/Image/{file_id}/raw` | pass | pass |
| `must-match-python` | `POST` | `/Message` | pass | pass |
| `must-match-python` | `POST` | `/RCH` | pass | pass |
| `must-match-python` | `PUT` | `/RCH` | pass | pass |
| `must-match-python` | `POST` | `/RTH` | pass | pass |
| `must-match-python` | `PUT` | `/RTH` | pass | pass |
| `must-match-python` | `GET` | `/Reticulum/Config` | pass | pass |
| `must-match-python` | `PUT` | `/Reticulum/Config` | pass | pass |
| `must-match-python` | `POST` | `/Reticulum/Config/Rollback` | pass | pass |
| `must-match-python` | `POST` | `/Reticulum/Config/Validate` | pass | pass |
| `must-match-python` | `GET` | `/Reticulum/Discovery` | pass | pass |
| `must-match-python` | `GET` | `/Reticulum/Interfaces/Capabilities` | pass | pass |
| `must-match-python` | `GET` | `/Status` | pass | pass |
| `must-match-python` | `DELETE` | `/Subscriber` | pass | pass |
| `must-match-python` | `GET` | `/Subscriber` | pass | pass |
| `must-match-python` | `PATCH` | `/Subscriber` | pass | pass |
| `must-match-python` | `POST` | `/Subscriber` | pass | pass |
| `must-match-python` | `POST` | `/Subscriber/Add` | pass | pass |
| `must-match-python` | `GET` | `/Subscriber/{subscriber_id}` | pass | pass |
| `must-match-python` | `GET` | `/Telemetry` | pass | pass |
| `must-match-python` | `DELETE` | `/Topic` | pass | pass |
| `must-match-python` | `GET` | `/Topic` | pass | pass |
| `must-match-python` | `PATCH` | `/Topic` | pass | pass |
| `must-match-python` | `POST` | `/Topic` | pass | pass |
| `must-match-python` | `POST` | `/Topic/Associate` | pass | pass |
| `must-match-python` | `POST` | `/Topic/Subscribe` | pass | pass |
| `must-match-python` | `GET` | `/Topic/{topic_id}` | pass | pass |
| `must-match-python` | `GET` | `/api/EmergencyActionMessage` | pass | pass |
| `must-match-python` | `POST` | `/api/EmergencyActionMessage` | pass | pass |
| `must-match-python` | `GET` | `/api/EmergencyActionMessage/latest/{team_member_uid}` | pass | pass |
| `must-match-python` | `GET` | `/api/EmergencyActionMessage/team/{team_uid}/summary` | pass | pass |
| `must-match-python` | `DELETE` | `/api/EmergencyActionMessage/{callsign}` | pass | pass |
| `must-match-python` | `GET` | `/api/EmergencyActionMessage/{callsign}` | pass | pass |
| `must-match-python` | `PUT` | `/api/EmergencyActionMessage/{callsign}` | pass | pass |
| `must-match-python` | `GET` | `/api/markers` | pass | pass |
| `must-match-python` | `POST` | `/api/markers` | pass | pass |
| `must-match-python` | `GET` | `/api/markers/symbols` | pass | pass |
| `must-match-python` | `DELETE` | `/api/markers/{object_destination_hash}` | pass | pass |
| `must-match-python` | `PATCH` | `/api/markers/{object_destination_hash}` | pass | pass |
| `must-match-python` | `PATCH` | `/api/markers/{object_destination_hash}/position` | pass | pass |
| `must-match-python` | `GET` | `/api/r3akt/assets` | pass | pass |
| `must-match-python` | `POST` | `/api/r3akt/assets` | pass | pass |
| `must-match-python` | `DELETE` | `/api/r3akt/assets/{asset_uid}` | pass | pass |
| `must-match-python` | `GET` | `/api/r3akt/assets/{asset_uid}` | pass | pass |
| `must-match-python` | `GET` | `/api/r3akt/assignments` | pass | pass |
| `must-match-python` | `POST` | `/api/r3akt/assignments` | pass | pass |
| `must-match-python` | `PUT` | `/api/r3akt/assignments/{assignment_uid}/assets` | pass | pass |
| `must-match-python` | `DELETE` | `/api/r3akt/assignments/{assignment_uid}/assets/{asset_uid}` | pass | pass |
| `must-match-python` | `PUT` | `/api/r3akt/assignments/{assignment_uid}/assets/{asset_uid}` | pass | pass |
| `must-match-python` | `GET` | `/api/r3akt/capabilities/{identity}` | pass | pass |
| `must-match-python` | `DELETE` | `/api/r3akt/capabilities/{identity}/{capability}` | pass | pass |
| `must-match-python` | `PUT` | `/api/r3akt/capabilities/{identity}/{capability}` | pass | pass |
| `must-match-python` | `GET` | `/api/r3akt/events` | pass | pass |
| `must-match-python` | `GET` | `/api/r3akt/log-entries` | pass | pass |
| `must-match-python` | `POST` | `/api/r3akt/log-entries` | pass | pass |
| `must-match-python` | `GET` | `/api/r3akt/mission-changes` | pass | pass |
| `must-match-python` | `POST` | `/api/r3akt/mission-changes` | pass | pass |
| `must-match-python` | `GET` | `/api/r3akt/missions` | pass | pass |
| `must-match-python` | `POST` | `/api/r3akt/missions` | pass | pass |
| `must-match-python` | `DELETE` | `/api/r3akt/missions/{mission_uid}` | pass | pass |
| `must-match-python` | `GET` | `/api/r3akt/missions/{mission_uid}` | pass | pass |
| `must-match-python` | `PATCH` | `/api/r3akt/missions/{mission_uid}` | pass | pass |
| `must-match-python` | `GET` | `/api/r3akt/missions/{mission_uid}/markers` | pass | pass |
| `must-match-python` | `DELETE` | `/api/r3akt/missions/{mission_uid}/markers/{marker_id}` | pass | pass |
| `must-match-python` | `PUT` | `/api/r3akt/missions/{mission_uid}/markers/{marker_id}` | pass | pass |
| `must-match-python` | `PUT` | `/api/r3akt/missions/{mission_uid}/parent` | pass | pass |
| `must-match-python` | `GET` | `/api/r3akt/missions/{mission_uid}/rde` | pass | pass |
| `must-match-python` | `PUT` | `/api/r3akt/missions/{mission_uid}/rde` | pass | pass |
| `must-match-python` | `GET` | `/api/r3akt/missions/{mission_uid}/zones` | pass | pass |
| `must-match-python` | `DELETE` | `/api/r3akt/missions/{mission_uid}/zones/{zone_id}` | pass | pass |
| `must-match-python` | `PUT` | `/api/r3akt/missions/{mission_uid}/zones/{zone_id}` | pass | pass |
| `must-match-python` | `GET` | `/api/r3akt/rights/definitions` | pass | pass |
| `must-match-python` | `DELETE` | `/api/r3akt/rights/grants` | pass | pass |
| `must-match-python` | `GET` | `/api/r3akt/rights/grants` | pass | pass |
| `must-match-python` | `PUT` | `/api/r3akt/rights/grants` | pass | pass |
| `must-match-python` | `DELETE` | `/api/r3akt/rights/mission-access` | pass | pass |
| `must-match-python` | `GET` | `/api/r3akt/rights/mission-access` | pass | pass |
| `must-match-python` | `PUT` | `/api/r3akt/rights/mission-access` | pass | pass |
| `must-match-python` | `GET` | `/api/r3akt/rights/subjects` | pass | pass |
| `must-match-python` | `GET` | `/api/r3akt/skills` | pass | pass |
| `must-match-python` | `POST` | `/api/r3akt/skills` | pass | pass |
| `must-match-python` | `GET` | `/api/r3akt/snapshots` | pass | pass |
| `must-match-python` | `GET` | `/api/r3akt/task-skill-requirements` | pass | pass |
| `must-match-python` | `POST` | `/api/r3akt/task-skill-requirements` | pass | pass |
| `must-match-python` | `GET` | `/api/r3akt/team-member-skills` | pass | pass |
| `must-match-python` | `POST` | `/api/r3akt/team-member-skills` | pass | pass |
| `must-match-python` | `GET` | `/api/r3akt/team-members` | pass | pass |
| `must-match-python` | `POST` | `/api/r3akt/team-members` | pass | pass |
| `must-match-python` | `DELETE` | `/api/r3akt/team-members/{team_member_uid}` | pass | pass |
| `must-match-python` | `GET` | `/api/r3akt/team-members/{team_member_uid}` | pass | pass |
| `must-match-python` | `GET` | `/api/r3akt/team-members/{team_member_uid}/clients` | pass | pass |
| `must-match-python` | `DELETE` | `/api/r3akt/team-members/{team_member_uid}/clients/{client_identity}` | pass | pass |
| `must-match-python` | `PUT` | `/api/r3akt/team-members/{team_member_uid}/clients/{client_identity}` | pass | pass |
| `must-match-python` | `GET` | `/api/r3akt/teams` | pass | pass |
| `must-match-python` | `POST` | `/api/r3akt/teams` | pass | pass |
| `must-match-python` | `DELETE` | `/api/r3akt/teams/{team_uid}` | pass | pass |
| `must-match-python` | `GET` | `/api/r3akt/teams/{team_uid}` | pass | pass |
| `must-match-python` | `GET` | `/api/r3akt/teams/{team_uid}/missions` | pass | pass |
| `must-match-python` | `DELETE` | `/api/r3akt/teams/{team_uid}/missions/{mission_uid}` | pass | pass |
| `must-match-python` | `PUT` | `/api/r3akt/teams/{team_uid}/missions/{mission_uid}` | pass | pass |
| `must-match-python` | `GET` | `/api/rem/peers` | pass | pass |
| `must-match-python` | `GET` | `/api/v1/app/info` | pass | pass |
| `must-match-python` | `GET` | `/api/v1/auth/validate` | pass | pass |
| `must-match-python` | `GET` | `/api/zones` | pass | pass |
| `must-match-python` | `POST` | `/api/zones` | pass | pass |
| `must-match-python` | `DELETE` | `/api/zones/{zone_id}` | pass | pass |
| `must-match-python` | `PATCH` | `/api/zones/{zone_id}` | pass | pass |
| `must-match-python` | `GET` | `/checklists` | pass | pass |
| `must-match-python` | `POST` | `/checklists` | pass | pass |
| `must-match-python` | `POST` | `/checklists/import/csv` | pass | pass |
| `must-match-python` | `POST` | `/checklists/offline` | pass | pass |
| `must-match-python` | `GET` | `/checklists/templates` | pass | pass |
| `must-match-python` | `POST` | `/checklists/templates` | pass | pass |
| `must-match-python` | `DELETE` | `/checklists/templates/{template_id}` | pass | pass |
| `must-match-python` | `GET` | `/checklists/templates/{template_id}` | pass | pass |
| `must-match-python` | `PATCH` | `/checklists/templates/{template_id}` | pass | pass |
| `must-match-python` | `POST` | `/checklists/templates/{template_id}/clone` | pass | pass |
| `must-match-python` | `DELETE` | `/checklists/{checklist_id}` | pass | pass |
| `must-match-python` | `GET` | `/checklists/{checklist_id}` | pass | pass |
| `must-match-python` | `PATCH` | `/checklists/{checklist_id}` | pass | pass |
| `must-match-python` | `POST` | `/checklists/{checklist_id}/feeds/{feed_id}` | pass | pass |
| `must-match-python` | `POST` | `/checklists/{checklist_id}/join` | pass | pass |
| `must-match-python` | `POST` | `/checklists/{checklist_id}/tasks` | pass | pass |
| `must-match-python` | `DELETE` | `/checklists/{checklist_id}/tasks/{task_id}` | pass | pass |
| `must-match-python` | `PATCH` | `/checklists/{checklist_id}/tasks/{task_id}/cells/{column_id}` | pass | pass |
| `must-match-python` | `PATCH` | `/checklists/{checklist_id}/tasks/{task_id}/row-style` | pass | pass |
| `must-match-python` | `POST` | `/checklists/{checklist_id}/tasks/{task_id}/status` | pass | pass |
| `must-match-python` | `POST` | `/checklists/{checklist_id}/upload` | pass | pass |
| `must-match-python` | `GET` | `/diagnostics/runtime` | pass | pass |
| `rust-additive-required` | `POST` | `/Control/Announce` | pass | missing-path |
| `rust-additive-required` | `POST` | `/Control/Start` | pass | missing-path |
| `rust-additive-required` | `GET` | `/Control/Status` | pass | missing-path |
| `rust-additive-required` | `POST` | `/Control/Stop` | pass | missing-path |
| `rust-additive-required` | `POST` | `/Control/Sync` | pass | missing-path |
| `rust-additive-required` | `GET` | `/events/system` | pass | missing-path |
| `rust-additive-required` | `GET` | `/messages/stream` | pass | missing-path |
| `rust-additive-required` | `GET` | `/openapi.yaml` | pass | missing-path |
| `rust-additive-required` | `GET` | `/telemetry/stream` | pass | missing-path |

## Release Decision Inputs

- Rust OpenAPI has no failed route probes for the matrix scope.
- Python OpenAPI has no failed route probes for must-match route contracts.
- Rust additive capability gates must still be backed by their named evidence commands before final release.
- True Python-visible mismatches must be fixed or explicitly waived; Rust additive failures block release even when Python does not expose an equivalent route.

## Workspace Status

```text
M .gitignore
 M README.md
 M crates/r3akt-rch-server/src/lib.rs
 M docs/release-contract-matrix.json
 M docs/release-parity-report.md
 M docs/release-readiness-audit.md
 M docs/rust-transition.md
 M scripts/local-reticulum-live-gate.ps1
 M scripts/python-rust-parity.ps1
```
