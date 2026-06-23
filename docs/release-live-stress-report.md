# RCH Rust Live Stress Test Report

Generated: 2026-05-16T11:58:30-03:00

## Scope

This report records the current live pre-release stress pass for the Rust RCH
server and shared UI. The active phone setup at the time of this pass is:

- Pixel 7 running REM: `6521979f1165965b24731061ef4a6906`
- Pixel 8a running REM: `b18494a51718a1fc6c1b15bdf76d4953`

Earlier S8/Sideband references are not part of this live pass because the phone
setup was changed to two REM phones.

## Build And Runtime

- Branch: `rust-next`
- Commit: `eebab80821610eb09f435eaca40f87ff2ef31463`
- Server binary: `target/release/r3akt-rch-server.exe`
- Server URL: `http://127.0.0.1:8081`
- API key used for manual testing: `manual-test`
- RCH LXMF destination: `761dfb354cfe5a3c9d8f5c4465b6c7f5`
- Server PID observed: initially `5436`; current restarted live PID `15540`
- reticulumd PID observed: `6872`
- reticulumd config: `target/manual-test/reticulumd.toml`
- RCH database: `target/manual-test/rch-manual.sqlite3`
- reticulumd database: `target/manual-test/reticulumd.sqlite3`

## Broadcast Timeout Repair Retest - 2026-06-23 UTC

Runtime under test:

- Branch: `codex/rch-user-story-audit`
- Server binary: `target/release/r3akt-rch-server.exe`
- Server URL: `http://127.0.0.1:18080`
- API key used for manual testing: `manual-test`
- RCH database: `RTH_Store/rch_state.sqlite3`
- RCH config: `RTH_Store/config.ini`
- Server PID after rebuild/restart: `24208`

Observed operator-reported row:

- Message `2a2892b3227b427487308d53712dd163` was reported by the UI as
  `failed` / `propagated` / `broadcast_direct_timeout_fallback` with
  `send_error`. After the existing propagated fallback repair path caught up,
  the configured SQLite store showed the row as `propagated` with
  `dispatch_status=accepted`, `delivery_method=propagated`,
  `delivery_policy_reason=broadcast_direct_timeout_fallback`, and
  `reticulumd_dispatch_count=13`.

New regression and live repair:

- Added a regression for persisted direct broadcast `send_timeout` rows that
  had already been marked `failed`.
- Rebuilt and restarted the local release binary against the configured DB and
  config.
- Historical failed direct broadcast timeout rows
  `f011f23619fc4d0b9dcd9bf51462629e` and
  `d3a43d4ff4844ccb9cb692d56a7b157c` were repaired by the running worker from
  `failed` / `direct` / `broadcast_direct` to queued propagated retries with
  `delivery_policy_reason=broadcast_direct_timeout_fallback` and
  `retry_reason=send_timeout`.
- A fresh live broadcast probe
  `096df17c-4569-4204-a11c-871064038b8a` timed out in direct broadcast mode
  and then converted to queued propagated fallback instead of terminal failure.

Current limitation:

- The local SDK/reticulumd path was rate-limited or slow during the probe, so
  several propagated fallback rows remained queued or in progress. The
  release-blocking behavior fixed here is that legitimate broadcast
  `send_timeout` rows no longer remain terminally failed; they are moved to
  propagation fallback and retried.

## Bounded Broadcast Stress Probe - 2026-06-23 UTC

Runtime under test:

- Branch: `codex/rch-user-story-audit`
- Server binary: `target/release/r3akt-rch-server.exe`
- Server URL: `http://127.0.0.1:18080`
- API key used for manual testing: `manual-test`
- RCH database: `RTH_Store/rch_state.sqlite3`
- RCH config: `RTH_Store/config.ini`
- Server PID observed: `3680`

Connected device inventory:

- `adb devices -l` showed Pixel 7 `35031FDH2003N8` and SM-G950W
  `988b9b344135304639`.
- Both phones had `network.reticulum.emergency` and `com.lxmf.messenger`
  installed and running by `pidof`.
- `/Client` included historical deck identities for `raphydeck`, `silkedeck`,
  and `corvodeck`.
- `/api/rem/peers` returned no current REM peer rows during this probe.

Broadcast probe:

- Posted `scope=broadcast` to `/Chat/Message`.
- Message ID: `2d437d80fbeb4c4cbc36c6fc3f9faeaa`
- Initial response persisted the row as `queued` with
  `delivery_policy_reason=broadcast_direct`, `method=direct`, and
  `dispatch_status=queued_deferred`.

Observed delivery-state progression:

- Polls 1-4: `state=queued`, `method=direct`, `dispatch_status=in_progress`.
- Poll 5: converted to `method=propagated`,
  `delivery_policy_reason=broadcast_direct_timeout_fallback`,
  `dispatch_status=queued`, `retry_reason=rate_limited`, and
  `error=SDK_SECURITY_RATE_LIMITED: per-ip request rate limit exceeded`.
- After the scheduled retry window, the row moved back to
  `dispatch_status=in_progress` with stale `error` and `retry_reason` metadata
  cleared, then hit the same SDK rate limit and was rescheduled with a later
  `next_attempt_at_ts_ms`; it did not become terminal `failed`.

Current limitation:

- This is a partial live-device pass. The corrected fallback/retry behavior is
  still working under pressure, but delivery to the connected phones/decks is
  not proven while the SDK/RNS path is rate-limited and `/api/rem/peers` is
  empty. Continue after the rate-limit window clears and require accepted/sent
  propagated dispatch evidence.

## Mission Audit/Event Export API Retest - 2026-06-23 UTC

Runtime under test:

- Branch: `codex/rch-user-story-audit`
- Server binary: `target/release/r3akt-rch-server.exe`
- Server URL: `http://127.0.0.1:18080`
- API key used for manual testing: `manual-test`
- RCH database: `RTH_Store/rch_state.sqlite3`
- RCH config: `RTH_Store/config.ini`
- Server PID observed: `3680`

Disposable run:

- Mission: `codex-us018-20260623014108`
- Explicit mission change: `codex-us018-change-20260623014108`
- Log entry: `codex-us018-log-20260623014108`

Passed checks:

- `/api/r3akt/events?limit=50&include_payload=false` returned the mission
  event history newest-first without serialized `payload` fields.
- `/api/r3akt/events?limit=50&include_payload=true` returned the same three
  mission events with payload data for export use.
- `/api/r3akt/mission-changes?mission_uid=...&include_delta=false` stripped
  `delta`, while `include_delta=true` returned the explicit change and the
  expected log-derived `ADD_CONTENT` change.
- `/api/r3akt/log-entries?mission_uid=...` returned only the disposable log.
- An export-shaped JSON object containing audit events, mission changes, and
  log entries round-tripped with the mission UID and collection counts intact.

Remaining gap:

- The API/export data path passed. Browser proof is still needed for expanding
  mission audit detail rows and triggering the actual `mission-audit-*.json`
  download from the shared UI.
- Follow-up in-app browser attempts to open
  `/missions?mission_uid=codex-us018-20260623014108` and then `/` timed out and
  reset the browser controller while `/Status` still reported healthy PID
  `3680`. Treat the rendered expand/download proof as blocked by the browser
  harness, not passed.

## TAK Connector RC Retest - 2026-06-23 UTC

Scope:

- Standalone TAK connector crate.
- Local loopback CoT send/receive coverage.
- Standalone `r3akt-tak-service` bridge tests.
- Documented external clear-TCP TAK profile `tcp://137.184.101.250:8087`.

Local tests:

- `cargo test -p r3akt-tak-connector tak_tcp_loopback_validates_bidirectional_cot_workflow`
  passed.
- `cargo test -p r3akt-tak-connector tak_proto_tcp_sender_pushes_stream_framed_protobuf_payload`
  passed.
- `cargo test -p r3akt-tak-connector service_bridges_rch_telemetry_and_chat_to_tak_cot_socket`
  passed.
- `cargo test -p r3akt-tak-connector service_bridges_inbound_tak_cot_to_rch_marker_route`
  passed.
- Full `cargo test -p r3akt-tak-connector` passed: 40 library tests and 5
  service binary tests.

External TCP TAK profile:

- A TCP reachability probe to `137.184.101.250:8087` succeeded.
- With `R3AKT_TAK_LIVE_COT_URL=tcp://137.184.101.250:8087`,
  `live_tak_server_accepts_keepalive_when_configured` passed.
- With the same outbound URL, `live_tak_server_accepts_reconnect_when_configured`
  passed.
- With both `R3AKT_TAK_LIVE_COT_URL` and
  `R3AKT_TAK_LIVE_INBOUND_COT_URL` set to the external TCP profile, the first
  inbound relay attempt connected but returned no payload after the probe.
  Rerunning the same configured test passed in 14.29 seconds.

Result:

- RCH-US-026 is current for RC: local loopback, protobuf framing, standalone
  sidecar bridge behavior, and the documented external clear-TCP TAK target
  all passed. The no-payload first inbound attempt is recorded as a transient
  external relay observation; no product code change was needed.

## Python Install/Import Migration RC Rehearsal - 2026-06-23 UTC

Scope:

- First-start Python import discovery and runtime file copy helpers.
- Core Python SQLite/config/telemetry migration.
- `migrate_python_rch` CLI behavior.
- Production migration wrapper dry-run and fixture apply behavior.

Commands:

- `cargo test -p r3akt-rch-server python_import`
- `cargo test -p r3akt-rch-core python_migration`
- `cargo test -p r3akt-rch-core parses_required_paths`
- `cargo test -p r3akt-rch-core migrates_database_and_config_from_parsed_args`
- `cargo test -p r3akt-rch-core reports_missing_required_paths_before_migrating`
- `powershell -ExecutionPolicy Bypass -File scripts/import-python-rch-production.Tests.ps1`

Passed checks:

- First-run import gating only prompts for new/empty Rust stores.
- Config-based Python source discovery recognizes `[migration].python_store`.
- Missing source normalization rejects absent stores and absent `rth_api.sqlite`
  files.
- Import by legacy database path copies `identity`, `reticulumd.identity`,
  `telemetry.db`, nested runtime files, imported topic rows, imported
  `python_config.*` settings, and records migration completion.
- Core migration imports identity/topic tables and R3AKT operational tables.
- CLI migrator parses required paths, imports config and telemetry into the
  target DB, and fails before mutating when required paths are missing.
- The production wrapper writes a dry-run `migration-plan.json`; fixture apply
  copies config, identity, Reticulum transport identity/config, telemetry DBs,
  files, images, LXMF data, `reticulumd.toml`, `rust-migration-report.json`,
  `migration-plan.json`, `migration-manifest.json`, and `MANIFEST.txt`.

Result:

- RCH-US-027 is current for RC against disposable Python-style stores. A real
  release deployment still needs a source-specific `-DryRun` against the actual
  Python store before applying the migration.

## Assets, Assignments, And Skills API Retest - 2026-06-23 UTC

Runtime under test:

- Branch: `codex/rch-user-story-audit`
- Server binary: `target/release/r3akt-rch-server.exe`
- Server URL: `http://127.0.0.1:18080`
- API key used for manual testing: `manual-test`
- RCH database: `RTH_Store/rch_state.sqlite3`
- RCH config: `RTH_Store/config.ini`

Disposable run:

- Prefix: `codex-us025-20260622232057`
- Created mission, team, team member, offline checklist, and task to provide
  valid assignment and requirement references.

Passed checks:

- Asset create, update, get, and `team_member_uid` list filter.
- Skill create, update, and list membership.
- Team-member skill create, update, and `team_member_rns_identity` list filter.
- Task skill requirement create, update, and `task_uid` list filter.
- Assignment create, update, and `mission_uid` plus `task_uid` list filter.
- Assignment asset set-empty, link, and unlink.
- Invalid asset member and invalid requirement skill references returned `404`.

Cleanup:

- Deleted the disposable asset, team member, and team.
- Tombstoned the disposable mission through the public mission delete route.

Remaining gap:

- The current public HTTP surface has no delete routes for skills,
  assignments, or task skill requirements. Namespaced skill/requirement/
  assignment rows from the live run remain as audit/history artifacts. Browser
  domain-object pages still need rendered create/edit/link proof before the UI
  side of RCH-US-025 is fully closed.

## UI Coverage

The following routes were exercised through browser automation against the live
server-served UI. No browser console errors or HTTP 4xx/5xx responses were
observed during these checks.

| Route | Result |
| --- | --- |
| `/` | Rendered |
| `/missions` | Rendered mission workspace and mission overview |
| `/missions/sar-spruce-ridge-2026/assets` | Rendered 7 mission assets |
| `/missions/sar-spruce-ridge-2026/log-entries` | Rendered mission logbook |
| `/checklists` | Rendered active checklist list and checklist detail |
| `/webmap` | Rendered MapLibre canvas and marker controls |
| `/topics` | Rendered topic hierarchy; Refresh action completed |
| `/files` | Rendered file registry; first file download event fired |
| `/chat` | Rendered direct-message lanes, but regular chat was not stressed further |
| `/users` | Rendered users, identities, REM peers, routing, teams, rights |
| `/configure` | Validate action completed; configuration reported valid |
| `/connect` | Test Connection action completed successfully |
| `/about` | Rendered runtime dossier and route inventory |

## REM Peer And User State

`/Client` contained exactly two current users:

- Pixel 7, REM capable, autonomous
- Pixel 8a, REM capable, autonomous

The REM peer discovery list also contained other active REM announces. This is
expected discovery data; fanout validation focused on the `/Client` users so
announces are not automatically treated as current users.

## Southbound REM Validation

### Checklist Create/Add/Complete

Checklist under test:

- `Pixel Pair REM Native 2026-05-16T14-08Z`
- `Pixel7 Pixel8a REM UI Stress 2026-05-16T14-55Z`

Observed generated REM commands:

- `checklist.create.online`
- `checklist.task.row.add`
- `checklist.task.status.set`

Observed human-readable LXMF bodies:

- `Checklist Pixel Pair REM Native 2026-05-16T14-08Z created`
- `Task Mission Briefing added`
- `Task Mission Briefing completed`

Delivery observations:

| Target | Result |
| --- | --- |
| Pixel 7 | Accepted by reticulumd and sent as `sent: link resource` |
| Pixel 8a | Direct link activation timed out; retry path sent `sent: propagated resource` for task completion |

Latest UI-created checklist fanout:

| Target | Message ID | Result |
| --- | --- | --- |
| Pixel 7 | `7d72dc47-1149-4572-9a0c-82e3a40f0a75` | `checklist.create.online`; accepted and sent as `sent: link resource` |
| Pixel 8a | `06b18b53-2042-49cc-b940-aeff8f9f5c93` | `checklist.create.online`; direct link timed out, then sent as `sent: propagated resource` after 6 attempts |

The latest UI-created checklist body was human-readable:

- `Checklist Pixel7 Pixel8a REM UI Stress 2026-05-16T14-55Z created`

reticulumd delivery traces:

- Pixel 7 message `7d72dc47-1149-4572-9a0c-82e3a40f0a75`: `queued`,
  `sending`, `sending: link resource`, `sent: link resource`.
- Pixel 8a base message `06b18b53-2042-49cc-b940-aeff8f9f5c93`: `queued`,
  `sending`, `failed: link activation timed out`.
- Pixel 8a retry message
  `06b18b53-2042-49cc-b940-aeff8f9f5c93-retry6-b18494a51718`: `queued`,
  `sending`, `sending: propagated resource`, `sent: propagated resource`.
  reticulumd log recorded propagation resource hash
  `e196f053348ac435f335e3d9e7512de01bc2a293085c82a6f4643034af843767`
  through propagation node `0f75ac15961b7d2b1577a57bdb1fda3c`.

### EAM Status Update

UI action:

- Mission Team screen, ALPHA-1 `COMMS` changed from `UNKNOWN` to `GREEN`

Observed generated REM command:

- `mission.registry.eam.upsert`

Delivery observations:

| Target | Result |
| --- | --- |
| Pixel 7 | Accepted by reticulumd and sent as `sent: link resource` |
| Pixel 8a | Direct link activation timed out; retry path sent `sent: propagated resource` |

## Current Release Risks

1. Pixel 8a direct link activation is consistently timing out from RCH.
   reticulumd resolves the cached peer identity and builds payloads addressed to
   `b18494a51718a1fc6c1b15bdf76d4953`, but the direct link does not activate.
   Propagation fallback succeeds at the transport layer.

2. Phone-side receipt is not fully proven for Pixel 8a from this automation
   pass. The server and reticulumd evidence proves that propagated resources
   were published, but the phone must confirm pickup in REM.

   Current runtime counters also show `reticulumd_inbound_received_total = 0`,
   so there is no server-observed reply path proving Pixel 8a applied the
   propagated checklist.

3. Pixel 8a's last imported announce in RCH remained
   `2026-05-16T14:02:27Z` during this pass, while Pixel 7 refreshed at
   `2026-05-16T14:52:00Z`.

4. reticulumd's `announces` table confirms the same asymmetry: Pixel 7 has
   repeated `R3AKT,EMergencyMessages,Telemetry;name=Pixel` announces through
   `2026-05-16T14:52:00Z`, while Pixel 8a has a single current
   `R3AKT,EMergencyMessages,Telemetry;name=Pixel8a` announce at
   `2026-05-16T14:02:27Z`.

5. reticulumd `sdk_identity_presence_list_v2` reports Pixel 8a with an older
   `name=emergency-ops-mobile` presence record from `2026-05-16T12:15:47Z`,
   even though the announce table has a newer Pixel8a app-data announce. This
   may be relevant to the direct-link timeout and should be investigated before
   release.

6. reticulumd `list_peers` shows a concrete health difference:

   - Pixel 7: `last_seen=2026-05-16T14:52:00Z`, `acceptance_rate=0.9815`,
     `sync_backoff=0`, `next_sync_attempt=0`.
   - Pixel 8a: `last_seen=2026-05-16T12:15:47Z`,
     `name=R3AKT,EMergencyMessages,Telemetry;name=emergency-ops-mobile`,
     `acceptance_rate=0.0000004847`, `sync_backoff=102`, and
     `next_sync_attempt=2026-05-16T15:48:25Z`.

   The runtime code path records announces separately from peered state when an
   announce does not qualify for autopeering. That explains why RCH can show the
   newer Pixel8a announce while reticulumd direct delivery still uses a stale
   peer record.

7. reticulumd's `messages` table contains propagated outbound rows for Pixel 8a
   with `_lxmf.method = "propagated"` and command payloads addressed to
   `b18494a51718a1fc6c1b15bdf76d4953`, including
   `checklist.task.status.set` and `mission.registry.eam.upsert`.

## Completion State

This stress pass is not complete enough to mark the release goal achieved until
both connected phones confirm receipt and application of the REM checklist and
EAM updates. Pixel 7 has strong server-side direct-delivery evidence. Pixel 8a
has propagation-publication evidence but still needs phone-side confirmation or
root-cause resolution of the direct-link timeout.

## Completion Audit

Objective restated as release criteria:

1. Compile the Rust RCH server and launch it with the shared UI.
2. Exercise the Web UI through a browser, covering each visible operator route
   and the major actions available without destructive data loss.
3. Use real Reticulum connectivity, not mocked or fake transports.
4. Verify southbound communication to the connected phones.
5. Record any release blockers or weakly verified areas instead of treating
   partial delivery evidence as complete success.

Prompt-to-evidence checklist:

| Requirement | Evidence | Status |
| --- | --- | --- |
| Rust server compiled | `target/release/r3akt-rch-server.exe` observed and running as PID `5436` | Verified |
| UI launched with server | Server used `ui/dist`; browser automation loaded UI routes from `http://127.0.0.1:8081` | Verified |
| Real Reticulum connectivity | External reticulumd process PID `6872`; `reticulumd_rpc` configured and running; live announce/event counters incremented | Verified |
| Browser exercised UI routes | `/`, `/missions`, `/checklists`, `/webmap`, `/topics`, `/files`, `/chat`, `/users`, `/configure`, `/connect`, `/about`, canonical mission assets, and canonical mission logbook all rendered | Verified |
| Non-destructive UI actions tested | Topic refresh, file download, config validate, connect test, checklist task completion, mission EAM status transition | Verified |
| REM users are current users, not all announces | `/Client` contained exactly Pixel 7 and Pixel 8a; REM peer discovery contained extra announces but fanout validation targeted current users | Verified |
| Checklist REM creation/add/status commands generated | `checklist.create.online`, `checklist.task.row.add`, and `checklist.task.status.set` observed in outbound LXMF fields | Verified |
| Checklist bodies are human-readable | Bodies included `Checklist ... created`, `Task Mission Briefing added`, and `Task Mission Briefing completed` | Verified |
| EAM REM command generated | `mission.registry.eam.upsert` observed for ALPHA-1 COMMS update | Verified |
| Pixel 7 southbound delivery | Checklist and EAM commands accepted and sent via `sent: link resource`; latest UI-created checklist create message `7d72dc47-1149-4572-9a0c-82e3a40f0a75` also sent by link | Verified server-side |
| Pixel 8a southbound delivery | Direct link timed out; propagation fallback published `sent: propagated resource` rows for checklist status, EAM, and latest UI-created checklist create retry `06b18b53-2042-49cc-b940-aeff8f9f5c93-retry6-b18494a51718` | Partially verified |
| Pixel 8a phone-side application | Requires REM app confirmation that propagated checklist/EAM updates appeared and applied | Not verified |
| Original S8/Sideband target | Superseded by current live setup of Pixel 7 and Pixel 8a both running REM | Not applicable to current setup |

Completion decision: not complete. The remaining release-blocking evidence gap is
Pixel 8a phone-side confirmation or a direct-link timeout root-cause fix.

## Continuation - Pixel 7 and Pixel 8a REM Pair

Date/time: 2026-05-16T15:17:52Z through 2026-05-16T15:25Z.

Current connected phones:

- Pixel 7 REM identity `6521979f1165965b24731061ef4a6906`.
- Pixel 8a REM identity `b18494a51718a1fc6c1b15bdf76d4953`.

Browser-control note: the in-app browser bridge and both fallback Playwright MCP
servers timed out or closed during this continuation. The test therefore drove
the same running server routes that the UI uses and verified the generated REM
messages through RCH persistence and reticulumd delivery traces.

Actions executed:

1. Created online checklist
   `stress-rem-p7-p8a-20260516T151752Z` named
   `Pixel 7 Pixel 8a REM Full Stack 20260516T151752Z`.
2. Added task `stress-rem-p7-p8a-task-20260516T151752Z` with human-readable
   body `Task Confirm REM checklist event fanout on Pixel 7 and Pixel 8a added`.
3. Completed the task with human-readable body
   `Task Confirm REM checklist event fanout on Pixel 7 and Pixel 8a completed`.
4. Updated ALPHA-1 EAM to GREEN with note
   `REM stress EAM update 20260516T151752Z for Pixel 7 and Pixel 8a`.

Server-side delivery evidence:

| Command | Pixel 7 | Pixel 8a |
| --- | --- | --- |
| `checklist.create.online` | `2f0aa77d-26e2-4753-8904-39cba8bbc015`, `sent: link resource` | `c38c9260-6b72-4d28-9457-c8d7a4d974c0`, direct link timed out, retry 6 `sent: propagated resource` |
| `checklist.task.row.add` | `8b1dba33-d1c7-404f-871f-e282419a04c8`, `sent: link resource` | `9062106d-6f3b-4369-8e10-008a76f5317a`, direct link timed out, retry 6 `sent: propagated resource` |
| `checklist.task.status.set` | `799c62d4-dd47-4b88-b19b-366f2b714711`, `sent: link resource` | `a2a6d0bf-c987-4645-956a-f955d6660ee4`, direct link timed out, retry 6 `sent: propagated resource` |
| `mission.registry.eam.upsert` | `4fca9e26-efdf-4270-8c59-6fba9ee7ed54`, `sent: link resource` | `35ccc7ef-05b6-4e02-bff3-668c1ed216c0`, direct link timed out, retry 6 `sent: propagated resource` |

Result: RCH generated the expected REM command envelopes for both connected REM
phones. Pixel 7 remains healthy on direct LXMF link delivery. Pixel 8a remains
reachable only through propagation fallback after repeated direct-link activation
timeouts. Phone-side confirmation is still required to prove that Pixel 8a
applied the propagated checklist and EAM updates in the REM application.

## Continuation - Browser-Created Checklist Rows

Date/time: 2026-05-16T15:25Z through 2026-05-16T15:49Z.

Browser evidence:

- A temporary Playwright runtime was installed under `target/stress-playwright`
  and used with system Chrome. This avoided source-tree package changes.
- The browser loaded `http://127.0.0.1:8081/checklists`, authenticated with
  API key `manual-test`, found
  `Pixel 7 Pixel 8a REM Full Stack 20260516T151752Z`, and showed the live
  checklist without console errors.
- Browser-driven Add actions created visible rows `Task 4` and `Task 5`.

Bug found and fixed during stress:

- UI-created rows that had no `legacy_value` or `notes` generated LXMF bodies
  such as `Task 78280e705cf34ceb94cc4c64aaa01bdb added`.
- This violated the human-readable REM checklist body requirement.
- Fix applied:
  - `crates/r3akt-rch-server/src/lib.rs`: REM checklist body generation now
    falls back to the task row number before `task_uid`.
  - `crates/r3akt-rch-core/src/lib.rs`: checklist task style/cell/status
    mission-change deltas now include `number`, so status updates can also use
    readable labels.
- Verification:
  - `cargo test -p r3akt-rch-server rem_checklist_command_body_uses_task_number_before_internal_uid`
  - `cargo test -p r3akt-rch-core standalone_checklist_task_status_emits_mission_change_for_current_user_fanout`
  - `cargo fmt --all -- --check`
  - Rebuilt and restarted `target/release/r3akt-rch-server.exe`; live process
    restarted as PID `15636`.

Live body verification after rebuild:

| Action | Pixel 7 | Pixel 8a |
| --- | --- | --- |
| Browser-created Task 4 add | `c7bd5e90-73e4-4438-b31f-ba6ebf8e499f`, body `Task 4 added`, `sent: link resource` | `edfbae3a-2e36-401d-bfa1-364f79c39fce`, body `Task 4 added`, direct link timed out during retry |
| Browser-created Task 5 add | `0b0edbfa-05cb-4265-99cc-ac72828f31c7`, body `Task 5 added`, `sent: link resource` | `4d1314c6-0f3b-4916-a322-899332f3050d`, body `Task 5 added`, direct link timed out then retry path attempted fallback |
| Task 5 status complete | `6d54d64b-1a29-4fe4-ac2d-8f0bd5021041`, body `Task 5 completed`, `sent: link resource` | `b1c05bc2-2242-48d9-908c-c9ab7783b35b`, body `Task 5 completed`, failed after seven attempts |

Additional blocker:

- Pixel 8a delivery is inconsistent. Earlier Pixel 8a commands reached
  `sent: propagated resource`, but Task 5 completion ended as
  `dispatch=failed`, `receipt=failed: link activation timed out`,
  `policy=rem_auto_propagation_fallback`.
- reticulumd trace for
  `b1c05bc2-2242-48d9-908c-c9ab7783b35b-retry6-b18494a51718` reached
  `sending: propagated resource` but never recorded `sent: propagated resource`.
- This is a release blocker until the fallback state transition either
  completes reliably or RCH reports the partial propagation failure with a clear
  operator-facing diagnostic.

## Continuation - Task 6 Propagation Fallback Probe

Date/time: 2026-05-16T16:01Z through 2026-05-16T16:07Z.

Live context:

- Server process: PID `15540`.
- Active REM peers:
  - Pixel 7: `6521979f1165965b24731061ef4a6906`, REM/autonomous.
  - Pixel 8a: `b18494a51718a1fc6c1b15bdf76d4953`, REM/autonomous.
- Checklist:
  `stress-rem-p7-p8a-20260516T151752Z`.
- New task:
  `81c991c7c8d04ca8b3fa6490c6a8ea47`, row number `6`.

Actions executed:

1. Added Task 6 through the running server.
2. Completed Task 6 through the running server.
3. Inspected persisted LXMF command envelopes and delivery metadata for both
   connected REM phones.

Server-side delivery evidence:

| Command | Pixel 7 | Pixel 8a |
| --- | --- | --- |
| `checklist.task.row.add` | `fd92f925-1711-4bdd-974b-e5313631bc2c`, body `Task 6 added`, `sent: link resource` | `2c8a7e8a-a0ef-40e1-9811-163f0aa9a896`, body `Task 6 added`, direct link timed out, retry 6 `sent: propagated resource` |
| `checklist.task.status.set` | `cadadc7f-fd3e-4838-a3cc-dea7281d32b3`, body `Task 6 completed`, `sent: link resource` | `fd4f0278-c484-44d2-b375-e37f8f4a4526`, body `Task 6 completed`, direct link timed out, retry 6 `sending: propagated resource`, `receipt_pending=true`, `receipt_active_extension_count=2` |

Result:

- Pixel 7 remains healthy for direct LXMF link delivery.
- Pixel 8a still cannot be reached by direct link during this run, but the
  propagation fallback path is active and no longer prematurely marks
  `sending: propagated resource` as a failed delivery.
- Human-readable REM checklist body generation is now verified for UI/API rows
  without `legacy_value` or `notes`: `Task 6 added` and `Task 6 completed`.
- Remaining release gate: phone-side confirmation that Pixel 8a applied the
  propagated Task 6 completion in REM. Server-side evidence currently proves
  active propagation, not application-level consumption on the phone.

Follow-up result after the active-extension cap:

- Pixel 8a Task 6 completion stayed at `sending: propagated resource` through
  `receipt_active_extension_count=10`, then RCH marked the row
  `dispatch=failed`, `error=delivery_receipt_timeout`,
  `receipt_timeout=true`.
- This is better than the earlier premature failure because the server now
  preserves the active reticulumd state while it is still active, but it remains
  a release blocker for Pixel 8a until the propagated completion either reaches
  `sent: propagated resource` or REM phone-side receipt confirms the update was
  applied despite the missing final reticulumd sent event.

## Continuation - EAM Follow-Up Against Two REM Phones

Date/time: 2026-05-16T16:08Z through 2026-05-16T16:12Z.

Action executed:

- Updated ALPHA-1 EAM with note
  `REM stress EAM followup 20260516T1608Z for Pixel 7 and Pixel 8a`.
- Generated REM command `mission.registry.eam.upsert` for both REM peers.

Server-side delivery evidence:

| Target | Message ID | Result |
| --- | --- | --- |
| Pixel 7 | `f4350f07-06b5-4d13-b668-f848306feee2` | `sent: link resource` |
| Pixel 8a | `b1b9bd5f-a9d8-498e-adc4-fc9be561027a` | Direct link timed out, retry 6 reached `sending: propagated resource`; still pending at `receipt_active_extension_count=4` |

Result:

- EAM fanout command generation is correct for both REM phones.
- Pixel 7 remains good on direct link.
- Pixel 8a again reaches propagation fallback but has not produced final
  `sent: propagated resource` evidence for this EAM follow-up yet.

Follow-up result:

- Pixel 8a EAM follow-up stayed at `sending: propagated resource` through
  `receipt_active_extension_count=10`, then RCH marked it
  `dispatch=failed`, `error=delivery_receipt_timeout`,
  `receipt_timeout=true`.
- reticulumd trace for
  `b1b9bd5f-a9d8-498e-adc4-fc9be561027a-retry6-b18494a51718` shows:
  `queued`, `sending`, `sending: propagated resource`, with no terminal
  `sent: propagated resource`.
- The comparable Pixel 8a Task 6 add retry
  `2c8a7e8a-a0ef-40e1-9811-163f0aa9a896-retry6-b18494a51718` did complete
  with `sent: propagated resource`, so the fallback path can succeed but is not
  reliable in the current live setup.

Root-cause evidence collected:

- Pixel 7 remains recently announced and directly reachable. Latest stored
  Pixel 7 announce: `2026-05-16T15:52:01Z`.
- Pixel 8a is stale from the RCH/reticulumd perspective. Latest stored Pixel
  8a announce: `2026-05-16T14:02:27Z`.
- Direct Pixel 8a attempts consistently resolve the cached peer identity, build
  payloads with the correct destination prefix, then fail with
  `link activation timed out`.
- Propagation fallback uses node `0f75ac15961b7d2b1577a57bdb1fda3c` (`rfed`,
  stamp cost `8`) according to reticulumd delivery traces, even though
  `propagation_status` reports `selected_node=null`.

Release implication:

- Pixel 8a cannot be counted as a fully connected REM peer in this stress pass
  until it announces again or the REM application confirms that it pulled and
  applied the propagated messages.
- The RCH Rust side correctly creates REM checklist and EAM command envelopes,
  but live southbound success is only fully proven for Pixel 7 in the current
  state.

RCH announce refresh:

- `announce_now` and `sdk_identity_announce_now_v2` were invoked successfully on
  reticulumd after the Pixel 8a failures.
- After 35 seconds, neither Pixel 7 nor Pixel 8a had produced a newer announce.
  Pixel 8a remained stale at `2026-05-16T14:02:27Z`.

Current UI confirmation:

- Browser automation reloaded `http://127.0.0.1:8081/users` against the current
  live server and captured
  `target/manual-test/stress-users-pixel7-pixel8a-current.png`.
- The Users screen rendered two users and three REM peers.
- Pixel 7 appeared as `ACTIVE`, `REM CLIENT`, `AUTONOMOUS`.
- Pixel 8a appeared as `SEEN`, `REM CLIENT`, `AUTONOMOUS`, with the stale last
  seen time still visible.
- No application console errors were observed. Font requests to `fonts.gstatic`
  were aborted by the headless browser and did not affect the app route.

Focused verification after this continuation:

- `cargo fmt --all -- --check`
- `cargo test -p r3akt-rch-server rem_checklist_command_body_uses_task_number_before_internal_uid`
- `cargo test -p r3akt-rch-core standalone_checklist_task_status_emits_mission_change_for_current_user_fanout`
- `cargo test -p r3akt-rch-server outbound_diagnostics_extends_active_reticulumd_propagation_receipt`
- `cargo test -p r3akt-rch-server reticulumd_auto_status_failure_requeues_rem_command_for_auto_retry`
- `cargo test -p r3akt-rch-server reticulumd_auto_status_failure_falls_back_to_propagation_after_retry_budget`
- `cargo test -p r3akt-rch-server rem_command_receipt_timeout_uses_extended_retry_budget`

All listed commands exited successfully. The cargo test filters also executed
secondary targets with zero matching tests; the named unit tests above each ran
and passed in their owning target.

Final completion audit for this continuation:

| Requirement | Current evidence | Release status |
| --- | --- | --- |
| Server and UI running | `r3akt-rch-server.exe` PID `15540`, UI served from `http://127.0.0.1:8081` | Verified |
| Real Reticulum connectivity | External `reticulumd.exe` PID `6872`, RPC `127.0.0.1:4243`, inbound event and announce counters moving | Verified |
| UI can show current REM peer state | `/users` browser check shows Pixel 7 and Pixel 8a as REM clients | Verified |
| Pixel 7 southbound REM | Direct link delivery for checklist and EAM commands | Verified server-side |
| Pixel 8a southbound REM | Direct link timeout; propagation sometimes reaches `sent: propagated resource`, but Task 6 completion and EAM follow-up timed out at `sending: propagated resource` | Blocked |
| Pixel 8a phone-side application | No new Pixel 8a announce after RCH announce refresh; no REM app confirmation in this pass | Not verified |
| Release decision | RCH command generation and Pixel 7 delivery are good; Pixel 8a is not fully proven as connected/applied | Not complete |

## Continuation - Pixel 8a Refresh Monitor

Date/time: 2026-05-16T16:25Z through 2026-05-16T16:28Z.

Purpose:

- Monitor real Reticulum state after the RCH announce refresh without sending
  additional duplicate checklist or EAM traffic.
- Check whether Pixel 8a re-announces, produces inbound traffic, or changes the
  release-blocking stale-peer condition.

Observed during the monitor window:

| Signal | Start | End |
| --- | --- | --- |
| reticulumd events seen | `2707` | `2900` |
| RCH imported announces | `7` | `8` |
| RCH inbound received | `0` | `0` |
| pending delivery receipts | `0` | `0` |
| outbound failed count | `164` | `164` |
| outbound queued count | `1` | `1` |
| Pixel 8a reticulumd announce timestamp | `1778940147` | `1778940147` |

Post-monitor `/Client` check:

- Pixel 7 refreshed to `2026-05-16T16:26:08Z`.
- Pixel 8a remained stale at `2026-05-16T14:02:27Z`.

Result:

- The Reticulum network and RCH inbound polling remained active during the
  monitor window.
- Pixel 7 re-announced and refreshed.
- Pixel 8a did not re-announce and did not produce inbound proof of receipt or
  REM-side application.
- This confirms the Pixel 8a blocker is current, not only historical evidence
  from earlier checklist/EAM sends.

## Continuation - TCP Interface Alignment Restart

Date/time: 2026-05-16T16:47Z through 2026-05-16T16:53Z.

Purpose:

- Separate Reticulum transport reachability from RCH code behavior.
- Configure the RCH test `reticulumd` with the same TCP peers visible from the
  two connected REM phones, then restart the live stack and run a small REM
  checklist fanout.

Runtime changes:

- Restarted `reticulumd.exe` as PID `3024`.
- Restarted `r3akt-rch-server.exe` as PID `15468`.
- Added these observed phone-side TCP peers to
  `target/manual-test/reticulumd.toml`:
  - `2603:c020:401f:d7af::a1:4242`
  - `2600:6c48:7009:801:a82b:3bdd:286d:88d9:4242`
  - `2604:5580:22::3e97:b34d:4242`
  - `62.151.179.77:4242`
- Kept the existing RCH TCP server listener `0.0.0.0:4242`, `rmap.world:4242`,
  and `137.184.101.250:4242`.

Observed TCP state after restart:

| Node | Established | Pending |
| --- | --- | --- |
| RCH host | `137.184.101.250:4242`, `2603:c020:401f:d7af::a1:4242`, `2604:5580:22::d99a:9dc:4242`, Pixel 7 local session `192.168.1.241 -> 192.168.1.121:4242` | none by the end of this sample |
| Pixel 7 | local session to `192.168.1.121:4242`, `2603:c020:401f:d7af::a1:4242` | `2600:6c48:7009:801:a82b:3bdd:286d:88d9:4242`, `2604:5580:22::3e97:b34d:4242` |
| Pixel 8a | `2603:c020:401f:d7af::a1:4242` | `62.151.179.77:4242`, `2600:6c48:7009:801:a82b:3bdd:286d:88d9:4242` |

Checklist under test:

- `stress-rem-tcp-exact-20260516T164955Z`
- Name: `REM Exact TCP Interface Stress 20260516T164955Z`
- Task: `Confirm REM delivery after exact TCP interface alignment`

Server/API result:

- `POST /checklists` succeeded.
- `POST /checklists/{id}/tasks` succeeded.
- `POST /checklists/{id}/tasks/{task_id}/status` succeeded.
- Generated human-readable REM bodies:
  - `Checklist REM Exact TCP Interface Stress 20260516T164955Z created`
  - `Task Confirm REM delivery after exact TCP interface alignment added`
  - `Task Confirm REM delivery after exact TCP interface alignment completed`

Delivery result:

| Command | Pixel 7 | Pixel 8a |
| --- | --- | --- |
| `checklist.create.online` | `873b29a3-1cc9-4275-9850-65db4bee3f05`, failed: `peer not announced` | `66f6f3d5-5256-4c4d-884b-f3b1dc04605d`, failed: `peer not announced` |
| `checklist.task.row.add` | `caafb836-bf48-4135-a5a8-da03817bc38f`, reticulumd trace ended `failed: link activation timed out` | `dfc04e79-0a0e-46aa-8969-3172cb0fd19c`, reticulumd trace ended `failed: link activation timed out` |
| `checklist.task.status.set` | `af56ef64-c02a-4342-955f-f0c2b6c8b651`, reticulumd trace ended `failed: link activation timed out` | `e562cc52-0be9-44ac-9a87-4ecaae1fe65c`, reticulumd trace ended `failed: link activation timed out` |

Classification:

- RCH code path: passed for API execution, REM command selection, `FIELD_COMMANDS`
  payload generation, and human-readable checklist bodies.
- Reticulum transport path: failed for this restart because no fresh phone
  announce was imported after the restart and reticulumd link activation timed
  out for both REM identities.
- Runtime behavior gap: RCH still attempted immediate fanout to DB-known REM
  peers whose current reticulumd runtime did not yet consider them announced.
  This should be made more operator-visible, and the retry/backoff behavior
  should avoid creating rate-limit pressure after a restart.

Release implication:

- TCP interface alignment improved the diagnostic clarity and preserved active
  network sessions, but it did not complete the live two-phone REM release gate.
- The remaining blocker is not REM payload compatibility. It is live Reticulum
  announce/link state after restart plus RCH runtime retry/rate-limit handling
  around that state.

## Continuation - Peer-Not-Announced Retry Fix

Date/time: 2026-05-16T17:02Z through 2026-05-16T17:05Z.

Code fix:

- `crates/r3akt-rch-server/src/lib.rs` now treats REM auto
  `failed: peer not announced` status as a retryable Reticulum runtime state
  instead of a terminal payload failure.
- The retry reason is recorded as `peer_not_announced`.
- The next attempt is delayed by the reticulumd announce-list poll window
  instead of the normal fast retry backoff, preventing restart-time fanout from
  increasing RPC rate-limit pressure while the daemon rebuilds announce/link
  state.

Regression coverage:

- Added and verified
  `reticulumd_auto_peer_not_announced_requeues_rem_command_with_announce_backoff`.
- Related checks still pass:
  - `cargo test -p r3akt-rch-server reticulumd_auto_peer_not_announced_requeues_rem_command_with_announce_backoff --lib`
  - `cargo test -p r3akt-rch-server reticulumd_auto_status_failure --lib`
  - `cargo test -p r3akt-rch-server outbound_retry_worker_rate_limit_backs_off_past_sdk_window --lib`
  - `cargo fmt --all -- --check`

Build and restart:

- Stopped the old `r3akt-rch-server.exe` that held
  `target/release/r3akt-rch-server.exe` open.
- Rebuilt with `cargo build --release -p r3akt-rch-server`.
- Restarted the release server as PID `5556`.
- Kept the real external `reticulumd.exe` running as PID `3024`.

Post-fix live probe:

- Checklist:
  `stress-rem-peer-retry-20260516T170326Z`.
- Name:
  `REM Peer Announce Retry Probe 20260516T170326Z`.
- The probe generated correct human-readable REM create bodies for both phones:
  `Checklist REM Peer Announce Retry Probe 20260516T170326Z created`.

Observed live delivery:

| Target | Message ID | Result |
| --- | --- | --- |
| Pixel 7 | `b4aaa855-b9b1-472c-81d2-039c9633906c` | reticulumd accepted the send, then stayed in `sending`; RCH queued retry after `delivery_receipt_timeout` |
| Pixel 8a | `1f5f9c51-8d58-4f80-b7a8-da34496b040f` | reticulumd accepted the send, then stayed in `sending`; RCH queued retry after `delivery_receipt_timeout` |

Additional live observations:

- Pixel 7 refreshed after the rebuild: `/Client` showed last seen
  `2026-05-16T17:01:37Z`.
- Pixel 8a remained stale at `2026-05-16T16:43:38Z`.
- `/diagnostics/runtime` showed live inbound polling and announce imports, but
  also recorded
  `reticulumd RPC SDK_SECURITY_RATE_LIMITED: per-ip request rate limit exceeded`.
- The browser MCP transports were closed during this continuation, so no new
  in-app browser screenshot was captured after the rebuild.

Classification:

- RCH REM payload generation: still verified.
- RCH restart-time `peer not announced` handling: fixed and unit-tested.
- Remaining RCH runtime stress issue: live poll/retry traffic can still trigger
  reticulumd SDK rate limiting under the two-phone stress workload.
- Remaining Reticulum/network issue: Pixel 8a still lacks fresh REM announce
  proof and neither phone produced a confirmed southbound REM application receipt
  for this probe.

Release implication:

- This continuation reduces false code failures after a reticulumd restart, but
  the release stress goal is still not complete.
- The next backend release gate should address reticulumd RPC rate-limit
  backoff across inbound polling and receipt polling before resuming repeated
  southbound fanout attempts.

## Continuation - Inbound RPC Rate-Limit Cooldown

Date/time: 2026-05-16T17:13Z through 2026-05-16T17:15Z.

Code fix:

- `crates/r3akt-rch-server/src/lib.rs` now backs off the reticulumd inbound
  worker when an event poll returns `SDK_SECURITY_RATE_LIMITED`.
- The worker skips the remainder of that tick and pauses before polling
  reticulumd events, messages, or announces again.
- This prevents the inbound worker from amplifying one SDK rate-limit response
  into repeated event/list/announce RPC pressure.

Regression coverage:

- Added and verified
  `reticulumd_inbound_worker_backs_off_after_sdk_rate_limit`.
- Related checks:
  - `cargo test -p r3akt-rch-server reticulumd_inbound_worker_backs_off_after_sdk_rate_limit --lib`
  - `cargo test -p r3akt-rch-server reticulumd_inbound_worker_imports_announces_when_message_poll_is_empty --lib`
  - `cargo test -p r3akt-rch-server reticulumd_auto_peer_not_announced_requeues_rem_command_with_announce_backoff --lib`
  - `cargo fmt --all -- --check`

Build and restart:

- Rebuilt with `cargo build --release -p r3akt-rch-server`.
- Restarted the release server as PID `28900`.
- Kept real `reticulumd.exe` running as PID `3024`.

Passive live monitor:

| Signal | Start | End |
| --- | --- | --- |
| `reticulumd_inbound.error_total` | `0` | `0` |
| `reticulumd_inbound.event_poll_errors_total` | `0` | `0` |
| `reticulumd_inbound.announce_poll_errors_total` | `0` | `0` |
| `reticulumd_inbound.event_polls_total` | `26` | `91` |
| `reticulumd_inbound.announce_polls_total` | `28` | `96` |
| `reticulumd_inbound.events_seen_total` | `109` | `183` |

Client state after restart:

- Pixel 7 REM identity `6521979f1165965b24731061ef4a6906` remained the freshest
  phone peer, last seen `2026-05-16T17:01:37Z`.
- Pixel 8a REM identity `b18494a51718a1fc6c1b15bdf76d4953` remained stale,
  last seen `2026-05-16T16:43:38Z`.

Classification:

- RCH inbound polling no longer self-triggers SDK rate-limit errors while idle
  in this live monitor window.
- This does not prove phone-side southbound REM application. The two-phone
  release gate remains blocked until Pixel 8a refreshes and both phones confirm
  received/applied checklist or EAM events.

## Continuation - Post-Restart Browser Smoke

Date/time: 2026-05-16T17:16Z through 2026-05-16T17:20Z.

Browser tooling:

- The browser MCP transports were still closed, so the post-restart UI smoke
  used the local Playwright runtime under `target/stress-playwright`.
- Browser launch used system Chrome at
  `C:/Program Files/Google/Chrome/Application/chrome.exe`.
- Authentication was configured in browser local storage with API key
  `manual-test`.

Routes exercised:

| Route | Result |
| --- | --- |
| `/` | Rendered dashboard, status `ONLINE`, no console/page errors |
| `/missions` | Rendered mission workspace, no console/page errors |
| `/missions/sar-spruce-ridge-2026/overview` | Rendered mission elements route, no console/page errors |
| `/missions/sar-spruce-ridge-2026/assets` | Rendered mission assets route, no console/page errors |
| `/missions/sar-spruce-ridge-2026/log-entries` | Rendered mission log entries route, no console/page errors |
| `/checklists` | Rendered checklist route, no console/page errors |
| `/webmap` | Rendered webmap route and live connection label, no console/page errors |
| `/topics` | Rendered topic registry route, no console/page errors |
| `/files` | Rendered file registry route, no console/page errors |
| `/chat` | Rendered communications route, no console/page errors |
| `/users` | Rendered user registry after data load, no console/page errors |
| `/users/teams/members` | Rendered team member assignment route, no console/page errors |
| `/configure` | Rendered configuration console, no console/page errors |
| `/connect` | Rendered local connection settings, no console/page errors |
| `/about` | Rendered system dossier, no console/page errors |

Artifacts:

- Summary JSON:
  `target/manual-test/ui-smoke-20260516T1716Z/summary.json`.
- Route screenshots:
  `target/manual-test/ui-smoke-20260516T1716Z/*.png`.
- Corrected loaded users screenshot:
  `target/manual-test/ui-smoke-20260516T1716Z/users-loaded.png`.
- REM peers tab screenshot:
  `target/manual-test/ui-smoke-20260516T1716Z/users-rem-peers-loaded.png`.

User and REM peer UI evidence:

- `/users` loaded `54 ENTRIES`, `USERS 2`, `IDENTITIES 29`, `REM PEERS 5`,
  `TEAMS 8`, and `TEAM MEMBERS 10`.
- The users tab displayed both current REM phone users:
  - Pixel: `6521979f1165965b24731061ef4a6906`, `REM CLIENT`, `AUTONOMOUS`.
  - Pixel8a: `b18494a51718a1fc6c1b15bdf76d4953`, `REM CLIENT`,
    `AUTONOMOUS`.
- The REM peers tab displayed call-sign style names rather than full capability
  strings:
  `POCO`, `PIXEL`, `EMERGENCY-OPS-MOBILE`, `PIXEL8A`, and `NOEMI`.

Classification:

- Browser UI route smoke: verified after the latest server rebuild.
- REM peer UI labeling: verified for the current `/api/rem/peers` data.
- This remains a UI/API render verification only; it does not satisfy the
  southbound phone receipt/application release gate.

## Continuation - Phone-Matched TCP Interface Restart

Date/time: 2026-05-16T17:31Z through 2026-05-16T17:35Z.

Reason:

- Separate Reticulum network reachability from RCH code behavior before
  continuing the release stress test.
- Minimize transport friction by aligning the RCH test reticulumd TCP client
  interfaces with the TCP peers observed on both connected REM phones.

Phone evidence:

- Pixel 7 (`35031FDH2003N8`) REM sockets:
  - Established local RCH path: `10.0.0.33 -> 192.168.1.121:4242`.
  - Established public peer:
    `2603:c020:401f:d7af::a1:4242`.
  - Pending public peers:
    `62.151.179.77:4242` and
    `2600:6c48:7009:801:a82b:3bdd:286d:88d9:4242`.
- Pixel 8a (`3C121JEKB11387`) REM sockets:
  - Established public peer:
    `2603:c020:401f:d7af::a1:4242`.
  - Pending public peers:
    `62.151.179.77:4242` and
    `2600:6c48:7009:801:a82b:3bdd:286d:88d9:4242`.
- Direct app-private REM config files were not readable through `run-as`
  because the installed package is not debuggable.
- Pixel 7 external export `/sdcard/Download/rch-peer-list.json` referenced
  `RCH-Rust-Live` destination `91b88974692dfc49bbf7cbe971e0cea9`; this appears
  to be a phone-side saved peer entry and does not match the current server
  `--reticulumd-source` argument `761dfb354cfe5a3c9d8f5c4465b6c7f5`.

RCH test config change:

- Updated `target/manual-test/reticulumd.toml` to keep:
  - TCP server `0.0.0.0:4242`.
  - TCP client `2603:c020:401f:d7af::a1:4242`.
  - TCP client `2600:6c48:7009:801:a82b:3bdd:286d:88d9:4242`.
  - TCP client `62.151.179.77:4242`.
- Removed RCH-only test clients from this run:
  `rmap.world:4242`, `137.184.101.250:4242`, and
  `2604:5580:22::3e97:b34d:4242`.

Restart:

- Restarted real `reticulumd.exe` as PID `24036`.
- Restarted `r3akt-rch-server.exe` as PID `21100`.
- Server remained reachable at `http://127.0.0.1:8081` with API key
  `manual-test`.

Post-restart network state:

| Endpoint | State |
| --- | --- |
| RCH TCP server `0.0.0.0:4242` | Listening |
| Pixel 7 local path `192.168.1.121:4242 <- 192.168.1.241` | Established |
| Shared public IPv6 peer `2603:c020:401f:d7af::a1:4242` | Established |
| Shared public IPv6 peer `2600:6c48:7009:801:a82b:3bdd:286d:88d9:4242` | `SYN-SENT` on RCH and both phones |
| Shared public IPv4 peer `62.151.179.77:4242` | `SYN-SENT` on RCH and both phones |

Post-restart RCH announce:

- Sent `POST /Control/Announce` after restart; RCH returned
  `{"status":"announce sent"}`.
- Both phones were foregrounded in REM at the time of the announce.

Current split between network and code:

- Network: RCH now matches the phones' observed public TCP peer set. The
  two peers that remain pending are also pending on the phones, so those are
  Reticulum network reachability conditions rather than RCH-specific TCP
  configuration defects.
- Network: Pixel 7 has a direct local TCP session into RCH. Pixel 8a does not
  currently show a direct local TCP session into RCH.
- Code/runtime: RCH continues polling `reticulumd` successfully after restart;
  `announce_poll_errors_total` stayed at `0` in the post-restart window.
- Code/runtime: `event_poll_errors_total` increased during the restart window
  and `last_cursor_reset_reason` reported that the persisted event cursor was
  ahead of the restarted reticulumd stream. That is a restart/cursor handling
  behavior to keep separate from TCP reachability.
- Release gate: Pixel 7 and Pixel 8a remained listed as REM users, but neither
  phone produced a fresh imported client announce during this window. Pixel 7
  last seen remained `2026-05-16T17:23:42Z`; Pixel 8a last seen remained
  `2026-05-16T16:43:38Z`.

## Phone-Matched TCP Interfaces, Identity Correction, And Retest

Time: `2026-05-16T18:05Z` to `2026-05-16T18:13Z`.

Reticulum network isolation work:

- Rechecked both connected REM phones through ADB.
- Pixel 7 active sockets:
  - Direct local RCH path:
    `10.0.0.33:40832 -> 192.168.1.121:4242` established.
  - Shared public peer:
    `2603:c020:401f:d7af::a1:4242` established.
  - Shared pending public peers:
    `62.151.179.77:4242` and
    `2600:6c48:7009:801:a82b:3bdd:286d:88d9:4242`.
- Pixel 8a active sockets:
  - Shared public peer:
    `2603:c020:401f:d7af::a1:4242` established.
  - Shared pending public peers:
    `62.151.179.77:4242` and
    `2600:6c48:7009:801:a82b:3bdd:286d:88d9:4242`.
  - No direct local RCH TCP path observed.
- Pixel 8a REM Settings reported `Node Config auto mode | 3 TCP endpoints`
  with named endpoints:
  `rns.beleth.net:4242`, `rns.quad4.io:4242`, and `firezen.com:4242`.
- RCH `target/manual-test/reticulumd.toml` was updated to use the same named
  TCP client interfaces:
  - `rns.beleth.net:4242`
  - `rns.quad4.io:4242`
  - `firezen.com:4242`
  - plus the local RCH listener `0.0.0.0:4242`.
- Restarted real `reticulumd.exe` as PID `16256`.
- Restarted `r3akt-rch-server.exe` as PID `26912`.
- Post-restart RCH sockets:
  - RCH listener `0.0.0.0:4242`: listening.
  - Pixel 7 local connection into RCH: established.
  - RCH to `rns.beleth.net` resolved peer: established.
  - RCH to `firezen.com`: `SYN-SENT`, matching the phones.
  - RCH to `rns.quad4.io` resolved IPv4 peer `75.133.206.221:4242`:
    `SYN-SENT`; phones were still attempting a Quad4 IPv6 address.

Test-data correction:

- Pixel 8a Settings showed the currently running REM app hash as
  `5c231773f221c687682b031709c210fc` with call sign `Noemi`.
- RCH's user list was still targeting stale Pixel8a identity
  `b18494a51718a1fc6c1b15bdf76d4953`.
- Removed stale `b18494a51718a1fc6c1b15bdf76d4953` from `/RCH`.
- Added current Pixel8a/Noemi identity
  `5c231773f221c687682b031709c210fc` to `/RCH`.
- Confirmed `/Client` now contains exactly the two current REM users:
  - Pixel: `6521979f1165965b24731061ef4a6906`
  - Noemi: `5c231773f221c687682b031709c210fc`

Checklist retest:

- Created online checklist
  `RCH TCP matched REM checklist 1811`.
- Created checklist UID:
  `78f1c4795541428da14b569106dd8fb4`.
- RCH accepted and persisted the checklist through `POST /checklists`.
- Outbound counters changed from `outbound_enqueued_total=260` to `262`,
  confirming two REM fanout messages were queued.
- `reticulumd` delivery trace for the pre-correction recipient set reported:
  - Pixel `6521979f1165965b24731061ef4a6906`:
    `failed: peer not announced`.
  - Stale Pixel8a `b18494a51718a1fc6c1b15bdf76d4953`:
    `failed: peer not announced`.

Current split between network/test-data/code:

- Network: RCH and the phones now use the same named public TCP bootstrap
  interface set, and Pixel 7 has a direct local TCP path into RCH.
- Network: after restarting `reticulumd`, neither current phone identity had a
  fresh usable path identity in the daemon; delivery failed at identity/path
  resolution before payload delivery.
- Test data: the Pixel8a user record was stale and has now been corrected to
  the phone's currently running REM identity.
- Code/runtime: RCH checklist creation and fanout queueing succeeded; the
  current blocker is fresh REM announces/path identity availability after the
  daemon restart, followed by a repeat send to the corrected two-user set.

## Exact REM TCP Endpoint Alignment Retest

Time: `2026-05-16T18:28Z` to `2026-05-16T18:30Z`.

Phone configuration capture:

- Pixel 8a / Noemi expanded REM Node Config showed `3 TCP endpoints`:
  - `rns.beleth.net:4242`
  - `rns.quad4.io:4242`
  - `firezen.com:4242`
- Pixel 7 / Pixel expanded REM Node Config showed `5 TCP endpoints`:
  - `rns.beleth.net:4242`
  - `rns.quad4.io:4242`
  - `firezen.com:4242`
  - `127.0.0.1:4242`
  - `192.168.1.121:4242`
- RCH kept `0.0.0.0:4242` as the server listener for the phone-side
  `192.168.1.121:4242` target. RCH was not configured to dial its own
  `127.0.0.1:4242` or `192.168.1.121:4242` listener as a client.

RCH configuration and restart:

- Updated `target/manual-test/reticulumd.toml` to use the same named public
  community endpoints as REM:
  - `rns.beleth.net:4242`
  - `rns.quad4.io:4242`
  - `firezen.com:4242`
  - local server listener `0.0.0.0:4242`
- Restarted real `reticulumd.exe` as PID `18340`.
- Restarted `r3akt-rch-server.exe` as PID `12424`.
- `/Status` returned HTTP `200` after restart.

Post-restart TCP evidence:

| Endpoint | RCH state | Phone state |
| --- | --- | --- |
| `0.0.0.0:4242` / `192.168.1.121:4242` | Listening; Pixel 7 local connection established | Pixel 7 established to `192.168.1.121:4242`; Pixel 8a no direct local RCH session |
| `rns.beleth.net:4242` | Established to `2603:c020:401f:d7af::a1:4242` | Pixel 7 and Pixel 8a established to same IPv6 peer |
| `rns.quad4.io:4242` | `SYN-SENT` to resolved IPv4 `75.133.206.221:4242` | Pixel 8a `SYN-SENT` to Quad4 IPv6 peer; Pixel 7 no fresh established Quad4 session observed |
| `firezen.com:4242` | `SYN-SENT` to `62.151.179.77:4242` | Pixel 7 and Pixel 8a also `SYN-SENT` to `62.151.179.77:4242` |

Fresh announce result:

- Triggered REM dashboard `Announce` actions on the phones after restart.
- RCH `/Client` still showed stale last-seen values:
  - Noemi `5c231773f221c687682b031709c210fc`:
    `2026-05-16T17:58:19Z`
  - Pixel `6521979f1165965b24731061ef4a6906`:
    `2026-05-16T17:51:52Z`
- RCH `/diagnostics/runtime` after the restart showed:
  - `reticulumd_inbound_announces_imported_total=0`
  - `reticulumd_inbound_announce_poll_errors_total=0`
  - `reticulumd_inbound_announce_poll_zero_total=53`
- Direct `reticulumd` `list_announces` showed old phone records only:
  - latest Noemi announce: `2026-05-16T17:58:19Z`
  - latest Pixel announce: `2026-05-16T17:51:52Z`
  - newest announce overall in the daemon store: `2026-05-16T18:26:19Z`,
    before this `reticulumd` restart.

Current classification:

- Reticulum network/runtime: even with phone-matched public endpoints and an
  established local Pixel 7 TCP session, this daemon has not received fresh
  Pixel or Noemi announces after restart.
- RCH code: RCH polling is healthy enough to report zero announce-poll errors;
  the current failure is before checklist payload delivery and before RCH can
  refresh phone paths.
- Release gate remains blocked until the daemon receives fresh current-phone
  announces and a corrected two-user checklist fanout can be repeated.

## Four-Endpoint Phone Baseline Retest

Time: `2026-05-16T18:39Z` to `2026-05-16T18:49Z`.

Configuration changes made on the live REM phones:

- Pixel 8a / Noemi: added local RCH TCP endpoint `192.168.1.121:4242`.
- Pixel 7 / Pixel: removed invalid phone-local endpoint `127.0.0.1:4242`.
- Both phones now show `4 TCP endpoints`:
  - `rns.beleth.net:4242`
  - `rns.quad4.io:4242`
  - `firezen.com:4242`
  - `192.168.1.121:4242`
- Broadcast remained enabled on both phones.

Post-change TCP evidence:

| Endpoint | Result |
| --- | --- |
| RCH listener | `reticulumd.exe` PID `18340` listening on `0.0.0.0:4242` |
| Pixel 7 local RCH session | Established to `192.168.1.121:4242` |
| Pixel 8a local RCH session | Established to `192.168.1.121:4242` |
| Shared public hub | Both phones established to `rns.beleth.net:4242` resolved as `2603:c020:401f:d7af::a1:4242` |
| Quad4 / FireZen public endpoints | Still observed in `SYN-SENT` on the phones and/or RCH |

Manual phone announce evidence:

- Pixel 7 emitted:
  - `[announce] sending reason=manual app=6521979f1165965b24731061ef4a6906 lxmf=fb4c70e20cfac047b899ca2f3671b50a`
  - It still logged public-interface transmit pressure:
    `iface: tx queue full timeout` on interfaces
    `/d86e8112f3c4c4442126f8e9f44f1686/` and
    `/35be322d094f9d154a8aba4733b8497f/`.
- Pixel 8a emitted:
  - `[announce] sending reason=manual app=5c231773f221c687682b031709c210fc lxmf=b5234f0c3d302a697ba883a8560f373e`
  - Immediate received traffic was observed on local interface
    `/f0a0278e4372459cca6159cd5e71cfee/`.

RCH and reticulumd result:

- RCH `/Client` did not refresh either phone:
  - Noemi remained at `2026-05-16T17:58:19Z`.
  - Pixel remained at `2026-05-16T17:51:52Z`.
- RCH `/diagnostics/runtime` after the manual announces:
  - `reticulumd_inbound_announces_imported_total=0`
  - `reticulumd_inbound_announce_poll_errors_total=0`
  - `reticulumd_inbound_announce_poll_zero_total=578`
- Direct `reticulumd` `list_announces` after both manual phone announces still
  showed only old phone records:
  - latest Noemi announce: `2026-05-16T17:58:19Z`
  - latest Pixel announce: `2026-05-16T17:51:52Z`
  - newest announce overall in the daemon store:
    `2026-05-16T18:42:33Z`

Current classification after TCP alignment:

- Reticulum network/runtime: both phones are now directly connected to RCH over
  TCP and both phones can emit manual REM announces, but this RCH reticulumd
  instance still does not receive fresh phone app-hash announce records.
- RCH code: no current evidence that RCH is dropping a received phone announce;
  direct daemon inspection shows the fresh phone announces are absent before
  RCH import.
- Retest boundary: do not use checklist fanout as a code verdict until
  reticulumd first shows fresh `6521979f1165965b24731061ef4a6906` and
  `5c231773f221c687682b031709c210fc` announce timestamps.

## Follow-up Correction: Fresh REM Announces Imported

Time: `2026-05-16T18:51Z` to `2026-05-16T18:54Z`.

The earlier conclusion that fresh phone announces were absent is no longer
current. After additional polling, `reticulumd` accepted and RCH imported fresh
REM announces from both current phones:

| Phone | REM app destination | RCH last_seen |
| --- | --- | --- |
| Pixel 7 / Pixel | `6521979f1165965b24731061ef4a6906` | `2026-05-16T18:53:38Z` |
| Pixel 8a / Noemi | `5c231773f221c687682b031709c210fc` | `2026-05-16T18:54:03Z` |

Reticulumd log evidence:

- Pixel accepted:
  `accepted dst=/6521979f1165965b24731061ef4a6906/ app_data=R3AKT,EMergencyMessages,Telemetry;name=Pixel`
- Noemi accepted:
  `accepted dst=/5c231773f221c687682b031709c210fc/ app_data=R3AKT,EMergencyMessages,Telemetry;name=Noemi`

RCH diagnostics after import:

- `reticulumd_inbound_announces_imported_total=35`
- `reticulumd_inbound_events_imported_total=33`
- `/Client` classified both peers as `client_type=rem` and `rem_mode=autonomous`.

Updated classification:

- Reticulum network/runtime: the TCP alignment did improve announce visibility.
  Both phones have established direct TCP sessions to the RCH listener and RCH
  now imports their REM app-hash announces.
- RCH code: announce import and REM peer classification are working for the two
  current phones after the phone/RCH TCP configuration was aligned.

## Checklist Fanout Retest After TCP Alignment

Time: `2026-05-16T19:00Z` to `2026-05-16T19:03Z`.

Test action:

- Created online checklist `RCH REM live checklist 160051` through the Rust
  northbound API on mission `sar-spruce-ridge-2026`.
- Created checklist uid: `090029f7ab154e6485425c3dd2d3b77e`.
- Expected fanout targets:
  - Noemi `5c231773f221c687682b031709c210fc`
  - Pixel `6521979f1165965b24731061ef4a6906`

RCH application-layer evidence:

- API returned HTTP `200`.
- Outbound delta after create:
  - `outbound_delivery.enqueued_total`: `+2`
  - `outbound_delivery.dispatch_accepted`: `+2`
  - `outbound_delivery.sent`: `+2`
  - `outbound_delivery.failed`: `+0`
- `/Events` showed `mission.registry.mission_change.upserted` with
  `recipient_count=2`, `sent=2`, and REM checklist command payloads carrying
  `command_type=checklist.create.online`.
- The payload body was REM-readable and included
  `name=RCH REM live checklist 160051`, checklist uid, mission uid, columns,
  participants, and `total_tasks=0`.

Reticulum runtime evidence:

- `reticulumd` resolved both REM app identities from cached peer identities.
- Direct link activation then failed for both destinations:
  - Noemi: `failed: link activation timed out`
  - Pixel: `failed: link activation timed out`
- RCH kept both messages queued with `delivery_method=auto`,
  `delivery_policy_reason=rem_auto`, and `retry_reason=rem_auto_status_failure`.

Phone UI evidence:

- Pixel 7 REM checklist screen did not show `RCH REM live checklist 160051`.
- Pixel 8a REM checklist screen did not show `RCH REM live checklist 160051`.

Current classification:

- Reticulum network/runtime: fresh announces and direct TCP sessions are present,
  but LXMF/Reticulum direct link activation from RCH `reticulumd` to both REM
  app destinations times out.
- RCH code: the Rust server currently creates the checklist, identifies the two
  REM peers, builds the REM `checklist.create.online` command, enqueues one
  targeted command per peer, and retries after runtime delivery failure.
- Release gate: blocked. The remaining live failure is end-to-end REM checklist
  delivery, currently at the `reticulumd` direct-link stage after RCH has handed
  off valid REM command messages.

## Checklist Fanout Retest After Bridge Auto Fix

Time: `2026-05-16T19:22Z` to `2026-05-16T19:24Z`.

Root cause separated from network:

- Network/runtime baseline was already green for this retest:
  - RCH `reticulumd` listened on `0.0.0.0:4242`.
  - Pixel 7 and Pixel 8a both had established TCP sessions to RCH.
  - `/Client` showed both current phones as REM peers:
    - Pixel `6521979f1165965b24731061ef4a6906`
    - Noemi `5c231773f221c687682b031709c210fc`
- Code issue found in the RCH bridge:
  - RCH recorded REM fanout as `delivery_method=auto`.
  - `r3akt-rch-bridge` stripped `"auto"` before calling `send_message_v2`.
  - Current `reticulumd` treats a missing `method` as direct-only, so the live
    daemon never received the intended auto/fallback instruction.

Fix:

- `crates/r3akt-rch-bridge/src/lib.rs` now maps outbound `"auto"` to
  `send_message_v2` params:
  - `method="direct"`
  - `try_propagation_on_fail=true`
- `direct` still uses `sdk_send_v2`.
- `propagated` is still passed through as `method="propagated"`.

Verification:

- `cargo test -p r3akt-rch-bridge outbound_` passed.
- `cargo build --release -p r3akt-rch-server` passed after stopping the locked
  running server executable.
- Restarted the Rust server on `http://127.0.0.1:8081` with the same API key,
  DB, UI dist path, and `reticulumd` RPC configuration.

Live retest:

- Created online checklist `RCH TCP aligned REM checklist 162257`.
- Created checklist uid: `423c54e1f7f24bd1bfb41e603493bcff`.
- RCH `/Events` showed `mission.registry.mission_change.upserted` with
  `recipient_count=2`, `sent=2`, and `command_type=checklist.create.online`.
- Reticulumd delivery traces:
  - Noemi message `1c45196f-c7be-49d9-861f-4f15af025810`:
    `queued -> sending -> sending: link resource -> sent: link resource`
  - Pixel message `e677d299-69e2-4c4f-b415-4768ecd77d55`:
    `queued -> sending -> sending: link resource -> sent: link resource`
- Phone UI evidence:
  - Pixel 7 screenshot `target/manual-test/rch_pixel7_after_patch.png` shows
    `RCH TCP aligned REM checklist 162257` at the top of REM Checklists.
  - Pixel 8a screenshot `target/manual-test/rch_pixel8a_after_patch.png` shows
    `RCH TCP aligned REM checklist 162257` at the top of REM Checklists.

Updated classification:

- Reticulum network/runtime: TCP interface alignment is now sufficient for both
  connected REM phones in this test.
- RCH code: the bridge auto-delivery mismatch was a real code issue and is now
  fixed for the current `reticulumd` contract.
- Release gate: REM checklist creation fanout is now verified end to end from
  RCH API through Reticulum delivery to both connected REM phone UIs.

Current process/socket confirmation:

- `r3akt-rch-server.exe` is running on `http://127.0.0.1:8081` with API key
  `manual-test`.
- `reticulumd.exe` PID `18340` is listening on `0.0.0.0:4242`.
- RCH Reticulum config advertises the same public TCP clients used by the
  phones: `rns.beleth.net:4242`, `rns.quad4.io:4242`, and `firezen.com:4242`.
- RCH also provides the local server endpoint the phones use directly:
  `192.168.1.121:4242` via the `0.0.0.0:4242` listener.
- Pixel 7 socket state: `10.0.0.33 -> 192.168.1.121:4242` established.
- Pixel 8a socket state: `10.0.0.35 -> 192.168.1.121:4242` established.

## Browser UI Smoke Retest After Backend Fix

Time: `2026-05-16T19:40Z` to `2026-05-16T19:42Z`.

Browser-tooling note:

- The Codex in-app browser connection and both exposed Playwright MCP browser
  transports were unavailable in this session:
  - in-app browser recovery/reset timed out;
  - `playwright/browser_navigate` returned `Transport closed`;
  - `playwright-2/browser_navigate` returned `Transport closed`.
- Fallback used for evidence collection: Microsoft Edge headless through local
  Chrome DevTools Protocol on port `9223`.

Connection state seeded in the browser:

- `baseUrl=http://127.0.0.1:8081`
- `authMode=apiKey`
- `apiKey=manual-test`

Route coverage:

| UI route | Browser result |
| --- | --- |
| `/` | Loaded; screenshot `target/manual-test/ui-smoke-cdp/dashboard.png` |
| `/missions` | Loaded; screenshot `target/manual-test/ui-smoke-cdp/missions.png` |
| `/missions/assets` | Loaded; router normalized to `/missions`; screenshot `target/manual-test/ui-smoke-cdp/mission-assets.png` |
| `/missions/logs` | Loaded; router normalized to `/missions`; screenshot `target/manual-test/ui-smoke-cdp/mission-logs.png` |
| `/checklists` | Loaded; screenshot `target/manual-test/ui-smoke-cdp/checklists.png` |
| `/webmap` | Loaded; screenshot `target/manual-test/ui-smoke-cdp/webmap.png` |
| `/topics` | Loaded; screenshot `target/manual-test/ui-smoke-cdp/topics.png` |
| `/files` | Loaded; screenshot `target/manual-test/ui-smoke-cdp/files.png` |
| `/chat` | Loaded; screenshot `target/manual-test/ui-smoke-cdp/chat.png` |
| `/users` | Loaded; screenshot `target/manual-test/ui-smoke-cdp/users.png` |
| `/users/teams/members` | Loaded; screenshot `target/manual-test/ui-smoke-cdp/team-roster.png` |
| `/configure` | Loaded; screenshot `target/manual-test/ui-smoke-cdp/configure.png` |
| `/connect` | Loaded; screenshot `target/manual-test/ui-smoke-cdp/connect.png` |
| `/about` | Loaded; screenshot `target/manual-test/ui-smoke-cdp/about.png` |

Sidebar click coverage:

- Browser-clicked primary navigation links for `/missions`, `/checklists`,
  `/webmap`, `/topics`, `/files`, `/chat`, `/users`, `/configure`, `/connect`,
  and `/about`; all navigated to the expected URL.

Browser diagnostics:

- Evidence artifact:
  `target/manual-test/ui-smoke-cdp/ui-smoke-report.json`.
- Captured browser errors: one canceled fetch,
  `net::ERR_ABORTED`, during navigation. No route failed to load from this
  event.
- The dashboard text scanner flagged `visibleError=true` because operational
  status text includes failure counters; route evidence did not show an
  authentication or rendering failure.

Post-build UI verification:

- Initial `npm --prefix ui run build` failed because `vite` was absent from the
  local `ui/node_modules` install.
- `npm --prefix ui ci` completed successfully and reported `0 vulnerabilities`
  with an engine warning for Node `v23.3.0`.
- `npm --prefix ui run build` then passed with Vite `6.4.2`.
- Re-ran the Edge/CDP smoke pass against the freshly built `ui/dist`:
  - artifact:
    `target/manual-test/ui-smoke-cdp-after-build/ui-smoke-report.json`;
  - route loads: `12/14` direct route loads reached the app shell before the
    timeout;
  - direct `/missions` and `/topics` captures timed out on the boot screen, but
    both routes loaded through sidebar click navigation immediately afterward;
  - primary sidebar clicks: `10/10` succeeded;
  - API auth failures: none confirmed in app route content;
  - app runtime errors: `0`;
  - captured console/network errors: `0`.

## Broadcast Timeout Fallback Retest

Time: `2026-06-22T22:06Z` to `2026-06-22T22:45Z`.

Runtime:

- RCH server: `target\release\r3akt-rch-server.exe`, PID `5740` after the
  final rebuild.
- State/config: `RTH_Store\rch_state.sqlite3` and `RTH_Store\config.ini`.
- Reticulumd RPC: `127.0.0.1:14243`.
- LXMF ZMQ command/response:
  `tcp://127.0.0.1:19100` / `tcp://127.0.0.1:19101`.

Observed messages:

| Message ID | Result |
| --- | --- |
| `2a2892b3227b427487308d53712dd163` | User saw a transient `failed/send_error` after direct-timeout propagation fallback. Live DB later showed current state `propagated`, method `propagated`, policy `broadcast_direct_timeout_fallback`, `reticulumd_dispatch_count=13`, six child rows with `sent: propagated resource`, and seven still `sending`. |
| `d3a43d4ff4844ccb9cb692d56a7b157c` | Post-retry-budget patch canary reproduced the remaining bug: direct broadcast stayed terminal `failed` with `error=send_timeout` instead of queueing propagation. |
| `89101f6a0bb04916b68aed1b31b1e21c` | After the direct-timeout fallback patch, direct broadcast timeout changed to queued `propagated` with policy `broadcast_direct_timeout_fallback`, `fallback_reason=direct_dispatch_timeout`, and no terminal failed state. Subsequent propagated attempts hit `SDK_SECURITY_RATE_LIMITED: per-ip request rate limit exceeded`, so the message stayed queued with retry scheduled. |
| `991ee56574b04ca59c0a5bd173a4c5b0` | After rebuilding with the rate-limit retry patch, the fallback canary remained queued through attempt 10 with `retry_scheduled=true`, `retry_reason=rate_limited`, and `SDK_SECURITY_RATE_LIMITED: per-ip request rate limit exceeded` instead of terminally failing at attempt 5. |

Fixes added:

- Worker-side direct broadcast/fanout dispatch timeouts now queue the same
  parent message for propagation instead of marking it failed after the direct
  retry budget is exhausted.
- Propagated broadcast/fanout fallback retries now allow the fifth propagated
  attempt before terminal failure, matching the observed daemon retry behavior.
- SDK rate-limit responses now use a longer delayed retry budget so transient
  backpressure does not consume the normal propagated fallback retry ceiling.
- Runtime diagnostics now count worker direct-timeout propagation fallback under
  `propagation_fallback_total`.

Remaining retest:

- Wait for the LXMF SDK rate-limit window to clear, then send another broadcast
  canary and confirm the queued propagated fallback reaches accepted propagated
  dispatch against the connected phones/decks. The current expected state while
  rate-limited is queued with delayed retry, not failed.

## Propagated Broadcast Failure Callback Retest

Time: `2026-06-22T23:12Z`.

Reported failure:

- Message ID `2a2892b3227b427487308d53712dd163`.
- UI showed `Delivery Method=propagated`,
  `Delivery Policy Reason=broadcast_direct_timeout_fallback`,
  `Failure Reason=send_error`, and `Route Type=broadcast`.

Result:

- The live SQLite row had recovered to `delivery_state=propagated`,
  `dispatch_status=accepted`, `attempts=5`, and a future retry timestamp, so
  the propagation fallback path was still active.
- Root cause in code: `/internal/delivery-failure` marked callbacks terminal
  failed without consulting the retry scheduler used by outbound dispatch.
- Added a server regression for a propagated broadcast fallback `send_error`
  callback. The callback now returns `retry_scheduled`, stores
  `delivery_state=queued`, preserves `delivery_method=propagated`, and records
  `retry_reason=send_error` instead of surfacing terminal failure.

Remaining retest:

- Restart the manual server with the callback fix, repeat broadcast canaries
  against the phones/decks, and confirm retry-eligible propagated fallback
  callbacks no longer appear as terminal `failed/send_error` in the UI.

## Propagated Broadcast Rate-Limit Budget Retest

Time: `2026-06-22T23:21Z` to `2026-06-22T23:43Z`.

Runtime:

- RCH server restarted from `target\release\r3akt-rch-server.exe` on
  `http://127.0.0.1:18080/`, PID `13732`, using `RTH_Store\rch_state.sqlite3`
  and `RTH_Store\config.ini`.
- Diagnostics confirmed `status=running`, outbound retry worker running,
  Reticulumd RPC configured, and LXMF SDK ZeroMQ configured.
- USB phones were attached as `Pixel_7` (`35031FDH2003N8`) and `SM_G950W`
  (`988b9b344135304639`). Both had `network.reticulum.emergency` version
  `1.1.2`; both apps were launched after the first canary because no PID was
  initially present.
- `/Client` still listed embedded peers `silkedeck`, `raphydeck`, and
  `corvodeck`, but the current announce evidence is stale for `silkedeck` and
  `raphydeck`; `corvodeck` was last seen earlier on `2026-06-22`.

Result:

- Canary `3fc2f131af65410c82badf99d5ec44a8` reproduced the remaining failure:
  direct broadcast timed out into `propagated` /
  `broadcast_direct_timeout_fallback`, hit SDK rate limiting, then a later
  `send_timeout` marked the message terminal `failed` at attempt 7.
- Root cause: the rate-limit path extended the current retry attempt, but a
  later non-rate-limit timeout recalculated max attempts from the smaller
  normal propagated fallback budget.
- Added a regression for this sequence and fixed retry metadata to persist
  `rate_limit_retry_budget=true` once SDK rate limiting has been encountered.
- After rebuilding and restarting, canary
  `dc8c20bc041b47f78c313f77eea916c1` stayed `queued` as `propagated` /
  `broadcast_direct_timeout_fallback` through attempt 8 with
  `retry_scheduled=true`, `rate_limit_retry_budget=true`, and global failed
  count flat at `37`.

Remaining retest:

- The queue no longer collapses to terminal `failed/send_error`, but live
  propagation is still blocked by `SDK_SECURITY_RATE_LIMITED: per-ip request
  rate limit exceeded`. Continue after the rate-limit window clears and confirm
  the queued propagated canary reaches accepted/sent propagation and appears on
  the phones/decks.

## Propagated Fallback Retry-Ceiling Retest

Time: `2026-06-23T00:30Z` to `2026-06-23T00:42Z`.

Trigger:

- User saw another broadcast failure card with `Delivery Method=propagated`,
  `Delivery Policy Reason=broadcast_direct_timeout_fallback`,
  `Failure Reason=send_error`, and `Route Type=broadcast`.

Evidence:

- `/Events` showed the latest terminal failure was canary
  `dc8c20bc041b47f78c313f77eea916c1`, not the earlier recovered
  `2a2892b3227b427487308d53712dd163` row.
- The event metadata had `rate_limit_retry_budget=true`, `attempts=30`,
  `delivery_method=propagated`, `delivery_policy_reason=broadcast_direct_timeout_fallback`,
  and `dispatch_timeout=true`. This proved the previous SDK rate-limit extension
  still allowed a terminal failure once the 30-attempt budget was exhausted.
- After the first rebuild, fresh canary
  `d0af7fcf-c651-4ecc-92f8-883845a3cff0` exposed a second ordering issue:
  the first default-budget direct broadcast `send_timeout` produced
  `message_delivery_retrying` with `delivery_method=direct` /
  `delivery_policy_reason=broadcast_direct` instead of immediately switching
  to propagation.

Fix:

- Direct broadcast/fanout dispatch timeouts now queue propagation before the
  ordinary direct retry budget is considered.
- Propagated broadcast/fanout messages that already came from a direct-timeout
  fallback now receive an extended propagation fallback retry ceiling
  (`120` attempts). This keeps `send_timeout` and later `send_error` attempts
  queued for propagation instead of producing a terminal `message_delivery_failed`
  event while the extended budget remains.
- Added regressions for:
  - default-budget direct broadcast timeout fallback ordering;
  - helper-level propagated broadcast fallback `send_timeout` after attempt 30;
  - stale propagated broadcast dispatch timeout finalization after attempt 30;
  - continuing propagated broadcast fallback `send_error` past the previous
    fifth-attempt ceiling.

Verification:

- `cargo fmt --all -- --check`
- `cargo test -p r3akt-rch-server propagated_broadcast_fallback_ -- --nocapture`
- `cargo test -p r3akt-rch-server outbound_diagnostics_queues_broadcast_direct_timeout_for_propagation -- --nocapture`
- `cargo test -p r3akt-rch-server outbound_diagnostics_keeps_propagated_broadcast_timeout_queued_after_rate_limit_budget -- --nocapture`
- `cargo clippy -p r3akt-rch-server --all-targets -- -D warnings`
- Rebuilt and restarted `target\release\r3akt-rch-server.exe` on
  `http://127.0.0.1:18080/`, PID `10352`, using the live
  `RTH_Store\rch_state.sqlite3` and `RTH_Store\config.ini`.
- Fresh canary `996a8718-7aa4-4a7a-bee4-e72c05cbcc66` emitted
  `message_propagation_queued` on the first direct timeout with
  `delivery_method=propagated` and `fallback_reason=direct_dispatch_timeout`.
  A later propagated timeout emitted `message_delivery_retrying` at attempt `2`
  with `delivery_policy_reason=broadcast_direct_timeout_fallback`; failed count
  stayed flat at `38`.
- Follow-up canary `c869fd1f3ffc405081c019a609324e80` reproduced the same
  operator-visible path after both USB phones were confirmed attached. The first
  direct broadcast attempt timed out, switched to `propagated` /
  `broadcast_direct_timeout_fallback`, and the next propagated timeout returned
  to `queued` with `retry_scheduled=true` and `retry_reason=send_timeout`
  instead of terminal `failed/send_error`.

Remaining retest:

- Phone/deck receipt remains unproven in this rate-limited environment. Continue
  watching for accepted/sent propagation once the SDK/RNS path stops timing out.

## Dashboard Runtime-Control Retest

Time: `2026-06-22T23:47Z` to `2026-06-23T00:18Z`.

Runtime:

- RCH server rebuilt and restarted from `target\release\r3akt-rch-server.exe`
  on `http://127.0.0.1:18080/`, PID `5012`, using
  `RTH_Store\rch_state.sqlite3`, `RTH_Store\config.ini`, API key
  `manual-test`, Reticulumd RPC `127.0.0.1:14243`, and LXMF ZMQ endpoints.
- The in-app browser loaded the Dashboard from the rebuilt `ui\dist` bundle.

Result:

- Before the fix, `/Control/Status` returned `port=null`; the Dashboard showed
  `Port: -` even though the server was bound to `127.0.0.1:18080`.
- `/Control/Announce` returned `announce sent`.
- `/Control/Sync` legitimately failed because the configured propagation RPC
  path timed out, but the Dashboard initially showed only a generic
  `Propagation sync failed` message. A 30-second UI request timeout could also
  mask the backend's 503 response detail.
- After the fix, `/Control/Status` includes the bound API host and port.
  Browser retest showed `PID: 5012` and `Port: 18080`.
- The Dashboard `Sync` action now waits for the backend propagation sync window
  and renders the backend error detail:
  `Propagation sync failed: outbound request failed: ... (os error 10060)`.

Remaining retest:

- No remaining RCH-US-004 issue from this slice. The failed propagation sync is
  a legitimate environment/runtime failure and is now visible to the operator.

## Remote Auth And Connection Retest

Time: `2026-06-23T00:20Z` to `2026-06-23T00:31Z`.

Runtime:

- RCH server remained on `http://127.0.0.1:18080/`, PID `5012`, using the live
  `RTH_Store` DB/config and API key `manual-test`.
- Browser test used `http://127.0.0.1.nip.io:18080` and
  `ws://127.0.0.1.nip.io:18080` as remote-looking URLs that resolve to the
  local RCH instance. This exercises remote-target auth behavior without an
  external hub.

Result:

- Connect switched from Local Connection Settings to Remote Connection mode and
  displayed `Remote backend requires authentication.`.
- While unauthenticated, clicking the protected Chat route redirected to
  `/connect?redirect=/chat`.
- API Key mode displayed
  `API key is required for remote backend authentication.` until an API key was
  entered.
- Login with API key `manual-test` reached the live server through the
  remote-looking URL and redirected back to `/chat`.
- Settings were restored to `http://127.0.0.1:18080`; Connect returned to Local
  Connection Settings and showed `Connection settings saved`.

Remaining retest:

- No RCH-US-003 product error found in this browser slice. A real deployed
  remote hub should still be checked for TLS/DNS/proxy behavior during staging
  or deployment testing.

## Config And Reticulum Path Retest

Time: `2026-06-22T22:41Z` to `2026-06-22T22:49Z`.

Runtime:

- RCH server: `target\release\r3akt-rch-server.exe`, PID `18500` after the
  final rebuild.
- State/config: `RTH_Store\rch_state.sqlite3` and `RTH_Store\config.ini`.
- Launch intentionally omitted `--reticulum-config-path` to verify
  `[hub].reticulum_config_path` fallback from the hub config.

Result:

- `/Config` returned the 1,162-byte hub config and `/Config/Validate` returned
  `valid=true`.
- Invalid hub config text returned `valid=false` with parser errors instead of
  mutating files.
- Before the fix, `/api/v1/app/info.reticulum_config_path` was empty and
  `/Reticulum/Config` returned an empty text payload even though
  `RTH_Store\config.ini` contained
  `reticulum_config_path = ~/.reticulum/config`.
- After the fix, `/api/v1/app/info.reticulum_config_path` resolved to
  `C:\Users\broth\.reticulum/config`, `/Reticulum/Config` returned the
  640-byte real Reticulum config, and `/Reticulum/Config/Validate` returned
  `valid=true`.
- The Configure page loaded without console errors. The Reticulum tab showed
  real values including `rmap` and `rmap.world`, and its header no longer showed
  the stale 1,162-byte Hub payload size while the Reticulum module was active.

Remaining retest:

- Exercise controlled apply/rollback against a temporary backup path or an
  operator-approved config edit before marking the full RCH-US-007 behavior
  complete.

## Controlled Config Apply/Rollback Retest

Time: `2026-06-22T22:53Z` to `2026-06-22T23:00Z`.

Runtime:

- Primary manual server remained running on `http://127.0.0.1:18080/`.
- Isolated temp server ran on `http://127.0.0.1:18081/`, PID `6576`, with
  temp hub and Reticulum config files under `%TEMP%` and API key `config-test`.
- No Reticulum daemon was attached to the isolated server; this retest only
  exercised file-backed config read, apply, backup, rollback, and UI state.

Result:

- `/Config` and `/Reticulum/Config` `PUT` created backup files and persisted
  temp edits.
- No-body rollback restored both temp files through the same endpoint shape used
  by the UI. PowerShell `Invoke-RestMethod` shaped one empty POST in a way that
  the endpoint rejected, but `curl.exe` and browser fetch no-body rollback
  succeeded.
- Hub Configure UI apply showed `Apply Result` and the backup path without
  console errors.
- Initial Hub UI rollback restored the file but left the editor showing the
  pre-rollback edited text and the status biased toward the earlier apply.
- After the UI store fix, Hub UI rollback refreshed the editor to the restored
  file text, showed `Rollback Result`, and changed the status pill to
  `Restored`.

Remaining retest:

- The Reticulum config API apply/rollback path passed, and the Reticulum store
  now reloads after rollback, but the Reticulum form toggle/apply/rollback path
  still needs a clean browser interaction pass. Direct switch interaction timed
  out in the current browser harness.

## Reticulum Form And BOM Config Retest

Time: `2026-06-23T00:34Z` to `2026-06-23T01:05Z`.

Runtime:

- Primary manual server remained on `http://127.0.0.1:18080/`.
- Isolated temp server ran on `http://127.0.0.1:18081/` with temp hub and
  Reticulum config files under `%TEMP%`, API key `config-test`, and no
  Reticulum daemon. Browser access used `127.0.0.1.nip.io:18081` so the UI
  exercised remote auth while still reaching the temp local server.

Reticulum form result:

- Configure > Reticulum loaded the temp Reticulum file and displayed
  `test_tcp` with `target_host = example.invalid`.
- Browser changed the target host to `example.org` and clicked Reticulum
  `Apply`; the UI showed `Reticulum config applied`.
- Browser clicked Reticulum `Rollback`; the UI showed `Rollback complete`,
  refreshed the form back to `example.invalid`, and no stale `example.org`
  value remained.
- Direct file check showed `hasRestoredHost=true`, `hasAppliedHost=false`, and
  `backupCount=1`.

BOM parser result:

- The temp setup exposed a Windows-specific issue: a hub `config.ini` written
  with PowerShell UTF-8 BOM did not resolve `[hub].reticulum_config_path` when
  `--reticulum-config-path` was omitted.
- Fixed `ini_value` to ignore a leading UTF-8 BOM before parsing section
  headers and added a regression test.
- Rebuilt the release binary and launched a fresh temp server without explicit
  `--reticulum-config-path`; `/api/v1/app/info.reticulum_config_path` matched
  the expected temp Reticulum config path and `/Reticulum/Config` returned the
  temp file.

Remaining retest:

- No remaining RCH-US-007 issue from this slice. The primary server was
  restarted after the release rebuild and remained healthy on
  `http://127.0.0.1:18080/`.

## Persisted Broadcast Fallback Repair Retest

Time: `2026-06-23T01:30Z` to `2026-06-23T01:50Z`.

Runtime:

- Rebuilt `target\release\r3akt-rch-server.exe` and restarted the primary
  manual server on `http://127.0.0.1:18080/`, PID `16648`.
- State/config remained `RTH_Store\rch_state.sqlite3` and
  `RTH_Store\config.ini`.
- Reticulumd RPC and LXMF ZeroMQ SDK endpoints remained configured.

Result:

- User-reported message `2a2892b3227b427487308d53712dd163` is currently
  `propagated` with `dispatch_status=accepted`, `reticulumd_dispatch_count=13`,
  and 13 propagated receipt targets. Its older `failed/send_error` system event
  was superseded by later retry and propagated state.
- Found eight persisted broadcast direct-timeout fallback rows that were
  stranded as terminal `failed` with retryable `send_timeout`, `send_error`, or
  rate-limit transport errors and no propagation dispatch count.
- Added a regression so failed propagated broadcast direct-timeout fallback rows
  are treated as retry-due only when the failure is retryable, dispatch count is
  still zero, and retry budget remains. Invalid-destination failures remain
  terminal.
- Fixed the repair path to set repaired rows back to `queued` when an attempt
  starts, and to let already-started repair attempts finalize through the stale
  dispatch timeout path without being selected repeatedly.
- After the final rebuild/restart, all eight stranded rows moved from
  `failed` to `queued`. After one dispatch timeout window, seven were queued
  with rate-limit backoff and one remained actively dispatching; none returned
  to terminal `failed`.

Remaining retest:

- The environment is still hitting `SDK_SECURITY_RATE_LIMITED`, so continue
  live phone/deck stress after the rate-limit window clears and confirm queued
  repaired fallbacks reach accepted/sent propagation.

## Superseded Broadcast Failure Event Retest

Time: `2026-06-23T02:39Z`.

Runtime:

- Rebuilt `target\release\r3akt-rch-server.exe` and restarted the primary
  manual server on `http://127.0.0.1:18080/`, PID `5748`.
- State/config remained `RTH_Store\rch_state.sqlite3` and
  `RTH_Store\config.ini`.
- Reticulumd RPC and LXMF ZeroMQ SDK endpoints remained configured.

Result:

- User again reported message `2a2892b3227b427487308d53712dd163` as
  `failed` / `propagated` /
  `broadcast_direct_timeout_fallback` with `send_error`.
- Live `/Chat/Messages?limit=200` showed the canonical message row is still
  `State=propagated`, `dispatch_status=accepted`,
  `reticulumd_dispatch_count=13`, and 13 propagated receipt targets. Six child
  rows were `sent: propagated resource`; seven remained `sending`.
- Live `/Events` no longer retained a `message_delivery_failed` row for the
  reported message and had no retained `message_delivery_failed` rows at all.
- Added a regression and formatter so `/Events` and `/events/system` replay
  reclassify stale `message_delivery_failed` events as
  `message_delivery_superseded` when the current message row has recovered to a
  non-failed state. The metadata now includes `original_event_type`,
  `delivery_failure_superseded=true`, `current_state`, and
  `current_dispatch_status` while preserving the current delivery metadata.

Remaining retest:

- A later pasted card showed the backend fix was not enough for an already-open
  dashboard event feed. The client-side merge fix is covered in the next
  section. Continue live phone/deck stress once the SDK rate-limit window
  clears.

## Dashboard Stale Broadcast Failure Card Retest

Time: `2026-06-23T02:58Z`.

Runtime:

- Primary manual server remained on `http://127.0.0.1:18080/`, PID `5748`.
- State/config remained `RTH_Store\rch_state.sqlite3` and
  `RTH_Store\config.ini`.
- API key `manual-test`.

Result:

- User pasted another dashboard failure card for the same broadcast message
  `2a2892b3227b427487308d53712dd163`: `Destination=Not set`,
  `State=failed`, `Delivery Method=propagated`,
  `Delivery Policy Reason=broadcast_direct_timeout_fallback`,
  `Failure Reason=send_error`, `Route Type=broadcast`.
- Live `/Chat/Messages?limit=500` showed the canonical row is still
  `State=propagated`, `dispatch_status=accepted`,
  `reticulumd_dispatch_count=13`, and 13 propagated receipt targets. Six child
  rows were `sent: propagated resource`; seven remained `sending`.
- Live `/Events?limit=500` returned zero current events for that message ID and
  zero current `message_delivery_failed` rows.
- Root HTTP serving check returned `200 text/html` from
  `http://127.0.0.1:18080/`.
- Added `ui/src/stores/dashboard.spec.ts` for the stale-card scenario and
  changed the dashboard event merge so a `message_delivery_superseded` event
  removes older `message_delivery_failed` rows for the same `MessageID`.
- Rebuilt `ui/dist` so the already-running manual server serves the refreshed
  dashboard bundle.

Verification:

- `npm --prefix ui run test -- dashboard` passed.
- `npm --prefix ui run build` passed.

Remaining retest:

- In-app browser control timed out while navigating to the local URL, so the
  rendered dashboard refresh remains a manual browser proof item. The running
  server is ready for manual reload at `http://127.0.0.1:18080/`.

Follow-up recheck:

- At `2026-06-23T03:30Z`, after the configured manual server was rebuilt and
  restarted as PID `18144`, the same reported message
  `2a2892b3227b427487308d53712dd163` was still persisted as
  `delivery_state=propagated`, `dispatch_status=accepted`,
  `delivery_method=propagated`, and
  `delivery_policy_reason=broadcast_direct_timeout_fallback`, with 13 receipt
  targets and no `send_error` on the current row.
- `/Events?limit=10000` returned no current event for that message ID. The
  selected in-app browser tab reported `about:blank` despite retaining the RCH
  title, and browser navigation to the local UI timed out, so the repeated card
  is treated as stale browser/dashboard state rather than a current backend
  failure.
- MessagePack decoding of the three newest terminal `failed` rows showed
  invalid test destination hashes (`codex-rch-us014-20260622222002`), not
  retryable propagated broadcast fallback `send_error` rows.

## Emergency Action Message API Retest

Time: `2026-06-23T02:00Z`.

Runtime:

- Primary manual server on `http://127.0.0.1:18080/`, PID `16648`.
- State/config remained `RTH_Store\rch_state.sqlite3` and
  `RTH_Store\config.ini`.
- API key `manual-test`.

Result:

- Created disposable team `codex-eam-team-1782179686` and EAM callsign
  `Codex EAM 1782179686`.
- `POST /api/EmergencyActionMessage` persisted the EAM and computed
  `overall_status=Yellow` from mixed Green/Yellow member status fields.
- Filtered list `GET /api/EmergencyActionMessage?team_uid=...&overall_status=yellow`
  returned the created EAM.
- `GET /api/EmergencyActionMessage/latest/{team_member_uid}` and
  `GET /api/EmergencyActionMessage/{callsign}` returned the same active record.
- `GET /api/EmergencyActionMessage/team/{team_uid}/summary` reported
  `total=1`, `active_total=1`, and `yellow_total=1`.
- `PUT /api/EmergencyActionMessage/{callsign}` changed medical status to Red
  and recomputed `overall_status=Red`.
- Validation checks passed: mismatched path/body callsign returned `400` with
  `callsign in body must match the path callsign`; confidence `1.1` returned
  `422` with `less_than_equal`.
- `DELETE /api/EmergencyActionMessage/{callsign}` returned the deleted record;
  follow-up get returned `404`; team summary reported `active_total=0` and
  `deleted_total=1`.
- Cleanup deleted the disposable team. Follow-up API checks showed
  `activeEamMatches=0` and `teamMatches=0`. The SQLite EAM tombstone remains
  with `deleted_ts_ms`, which is expected for summary/history semantics.

Remaining retest:

- Browser proof for the embedded mission/member EAM controls remains open; the
  route/API behavior itself passed against the live configured server.

## Team Roster And Rights API Retest

Time: `2026-06-23T02:52Z`.

Runtime:

- Primary manual server on `http://127.0.0.1:18080/`, PID `5748`.
- State/config remained `RTH_Store\rch_state.sqlite3` and
  `RTH_Store\config.ini`.
- API key `manual-test`.

Result:

- Created disposable mission/team/member run `codex-us015-20260623025150`.
- Rights definitions exposed `mission.registry.log.read` and role bundles.
- Team create/update/list/filter/get and team mission link/list/unlink passed.
- Member create/update/list/filter/get and member client link/list/unlink
  passed; member update used canonical role token `TEAM_LEAD`.
- Rights subjects listed the mission team member.
- Operation right grant/list/revoke passed for `mission.registry.log.read`.
- Mission access assign/list/revoke passed for `MISSION_OWNER`.
- Validation probes returned expected statuses: grant query missing
  `subject_type` returned `400`, missing member clients returned `404`, and
  display-label role `Team Lead` returned `400`.
- Cleanup deleted member/team/mission and verified zero active
  member/team/access rows for the disposable prefix.

Remaining retest:

- Browser proof for `UsersPage`, `TeamRosterPage`, and
  `TeamRightsMatrixPanel` create/edit/link/revoke feedback remains open.
- Confirm the UI submits canonical role values such as `TEAM_LEAD` instead of
  display labels such as `Team Lead`, or add UI mapping/error handling if
  needed.

## Checklist And Template API Retest

Time: `2026-06-23T03:25Z`.

Runtime:

- Primary manual server on `http://127.0.0.1:18080/`, rebuilt and restarted as
  PID `18144`.
- State/config remained `RTH_Store\rch_state.sqlite3` and
  `RTH_Store\config.ini`.
- API key `manual-test`.
- Reticulumd RPC `127.0.0.1:14243`; LXMF ZMQ command/response endpoints
  `tcp://127.0.0.1:19100` and `tcp://127.0.0.1:19101`.

Finding and fix:

- Disposable run `codex-us019-20260623001705` reproduced a checklist UI
  contract bug: `POST /checklists` with a valid `template_uid` and
  `mission_uid` persisted the link but returned only `mission_id`, leaving
  `mission_uid` empty for UI raw records.
- Added regression
  `checklist_from_template_returns_mission_uid_alias`.
- Fixed `RchCore::checklist_value` to emit both `mission_id` and
  `mission_uid`, preserving the existing Python-compatible alias while matching
  the Rust UI contract.

Verification:

- `cargo test -p r3akt-rch-server checklist_from_template_returns_mission_uid_alias -- --nocapture`
  failed before the fix with `mission_uid` as `Null`, then passed after the
  serializer change.
- `cargo test -p r3akt-rch-server checklist_ -- --nocapture` passed
  19 checklist-related server tests with 2 ignored legacy generic-fanout tests.
- `cargo test -p r3akt-rch-core checklist_ -- --nocapture` passed 9
  checklist-related core tests.
- `cargo build --release -p r3akt-rch-server` passed after stopping the old
  manual server process that had the release binary locked.

Live retest:

- Created disposable run `codex-us019-20260623002534`.
- Template create, patch, clone, and delete passed; valid template columns
  included exactly one pinned `DUE_RELATIVE_DTG` system column.
- Template-derived checklist create returned both
  `mission_id=codex-us019-20260623002534-mission` and
  `mission_uid=codex-us019-20260623002534-mission`.
- Task add returned task `a6dc2dbc961d4076be2cccc8731bbba5`.
- Cell patch persisted `Bring spare battery`.
- Row style persisted `#223344` and `line_break_enabled=true`.
- Task status changed to `COMPLETE`.
- Join, upload, and feed publish passed.
- CSV import `923d37d274744287ae75202ea65d7fdb` preserved three columns and
  two task rows.
- Task delete removed the disposable task.
- Cleanup deleted the checklist, CSV import checklist, clone/template, and
  mission; follow-up API verification showed zero active disposable checklists,
  zero matching templates, zero active disposable missions, and one expected
  deleted mission tombstone.

Remaining retest:

- Browser proof for checklist modals, CSV picker/preview, and delete
  confirmation remains open. The route/API behavior itself passed against the
  live configured server.

## Topic Asset Association API Retest

Time: `2026-06-23T03:49Z`.

Runtime:

- Primary manual server on `http://127.0.0.1:18080/`, PID `18144`.
- State/config remained `RTH_Store\rch_state.sqlite3` and
  `RTH_Store\config.ini`.
- API key `manual-test`.

Result:

- Created disposable topic `codex-us008-20260623004949` and explicit
  subscriber `codex-us008-20260623004949-subscriber` with random destination
  `83146ad350e7429bbd8846c0c80a0a7e`.
- Uploaded a text file and PNG image through `/Chat/Attachment`.
- `PATCH /File/{id}` and `PATCH /Image/{id}` with
  `TopicID=codex-us008-20260623004949` persisted the topic association.
- `/File` and `/Image` list responses showed the associated `TopicID`.
- Patching the file with `TopicID=null` detached it.
- Deleting the topic cleared the still-linked image `TopicID`, covering the
  cleanup path used when topic cards are removed.
- Cleanup deleted the subscriber, topic, file, and image. Follow-up list checks
  showed zero matching disposable topics and subscribers.

Remaining retest:

- Browser proof for the Topics page Manage Assets modal attach/detach feedback
  and topic/subscriber delete confirmation remains open.

## Dashboard Event Snapshot Reconciliation Retest

Time: `2026-06-23T03:56Z`.

Runtime:

- Primary manual server on `http://127.0.0.1:18080/`, PID `18144`.
- State/config remained `RTH_Store\rch_state.sqlite3` and
  `RTH_Store\config.ini`.
- API key `manual-test`.

Finding and fix:

- User again saw the broadcast delivery card for
  `2a2892b3227b427487308d53712dd163` as `failed` / `propagated` /
  `broadcast_direct_timeout_fallback` with `send_error`.
- Live SQLite and `/Chat/Messages?limit=500` both showed exactly one current
  row for that message: `State=propagated`, `dispatch_status=accepted`,
  `reticulumd_dispatch_count=13`, with six propagated child targets already
  `sent: propagated resource`.
- `/Events?limit=500` had no current event for `2a289...` and no current
  `message_delivery_failed` event for the message.
- The remaining issue was an open-dashboard stale-state gap: a tab that missed
  a superseded/recovery event could keep the old failure card in memory.
- Added dashboard store replacement from authoritative `/Events` snapshots.
  Periodic dashboard refresh now clears in-memory failure rows that are absent
  from the server event snapshot.

Verification:

- `npm --prefix ui run test -- dashboard` failed before the fix with
  `dashboard.replaceEvents is not a function`.
- After adding `replaceEvents` and wiring dashboard refresh to
  `/Events?limit=200`, `npm --prefix ui run test -- dashboard` passed.
- `npm --prefix ui run lint`, `npm --prefix ui run test`, and
  `npm --prefix ui run build` passed. The local server returned `200` for `/`
  and served the rebuilt `assets/index-D9w_tpHe.js` bundle.

Remaining retest:

- In-app browser navigation to the local UI timed out during this slice, so
  rendered proof remains open. Refresh the browser tab and confirm the event
  feed no longer shows the stale `2a289...` failure card.

## Marker And Zone API Retest

Time: `2026-06-23T04:03Z`.

Runtime:

- Primary manual server on `http://127.0.0.1:18080/`, PID `18144`.
- State/config remained `RTH_Store\rch_state.sqlite3` and
  `RTH_Store\config.ini`.
- API key `manual-test`.

Result:

- Created disposable mission `codex-us021-20260623040349-mission`.
- `/api/markers/symbols` included the default `marker` symbol with
  `mdi=map-marker`.
- Created marker `623b9d1b7b8b4dfbbebce05aeadf7ca8`, listed it with the
  expected name and `position={lat:45.5017, lon:-73.5673}`, moved it through
  `/api/markers/{id}/position`, renamed it through `/api/markers/{id}`, and
  deleted it during cleanup.
- Created alias marker `d0c1916c42f540409f014f3023276451` using
  `type=car` and `symbol=uav`; list output normalized it to
  `type=vehicle`, `symbol=drone`, and `category=drone`.
- Unsupported marker type returned `422`.
- Created zone `7fcf60c32f8146b4a038d4a2be4be0d0`, listed it with three
  points, patched name and geometry, and deleted it during cleanup.
- One-point zone creation returned `422`.
- Linked the zone and marker to the disposable mission with
  `/api/r3akt/missions/{mission_uid}/zones/{zone_id}` and
  `/api/r3akt/missions/{mission_uid}/markers/{marker_id}`.
- Mission link lists returned the expected zone and marker IDs, then unlink
  routes removed both IDs.
- `/Events?limit=500` included marker create/update/delete/telemetry events
  and mission marker/zone link/unlink events for the disposable artifacts.
- `/Telemetry?since=0` retained the marker deleted telemetry row for
  `623b9d1b7b8b4dfbbebce05aeadf7ca8`.
- Cleanup deleted the marker, alias marker, zone, and mission. Follow-up list
  checks showed zero active disposable markers, zones, or missions, with one
  expected deleted mission tombstone.

Remaining retest:

- Browser proof for MapLibre rendering, marker placement/radial menu, zone
  drawing/edit/delete, mission assignment popovers, icon fallback, and stale
  overlay cleanup after delete remains open.

## Post-Budget Broadcast Fallback Retry Repair

Time: `2026-06-23T04:24Z`.

Runtime:

- Primary manual server on `http://127.0.0.1:18080/`, restarted from rebuilt
  release binaries during the retest; final running PID is `3680`.
- State/config remained `RTH_Store\rch_state.sqlite3` and
  `RTH_Store\config.ini`.
- API key `manual-test`.

Finding and fix:

- User again reported broadcast message
  `2a2892b3227b427487308d53712dd163` with `Delivery Method=propagated`,
  `Delivery Policy Reason=broadcast_direct_timeout_fallback`, and
  `Failure Reason=send_error`.
- Live SQLite and `/Chat/Messages?limit=500` showed the canonical row was not
  failed: `State=propagated`, `dispatch_status=accepted`,
  `delivery_method=propagated`, `reticulumd_dispatch_count=13`, and no current
  `error` or `retry_reason`.
- The live DB also contained older retryable propagated fallback rows that had
  exhausted the previous fallback retry ceiling and stayed terminal `failed`
  under rate-limit/timeout pressure.
- Changed retry scheduling so retryable propagated broadcast/fanout
  direct-timeout fallback errors continue as queued propagation even after the
  previous 120-attempt ceiling instead of falling through to terminal failed.
- Changed the failed-row repair predicate so already-failed retryable propagated
  fallback rows are due for repair even after the old retry budget is exceeded.
- Cleared stale `error`, `retry_reason`, and `last_attempt_failed_at_ts_ms`
  metadata when a retry attempt starts, and cleared stale failed-at metadata
  when a later dispatch reaches `sent`, `delivered`, or `propagated`.
- Sanitized `/Chat/Messages` serialization for already-persisted successful
  rows so older recovered messages no longer expose stale failure metadata to
  UI detail renderers.

Verification:

- `cargo test -p r3akt-rch-server
  propagated_broadcast_fallback_retryable_error_stays_queued_after_retry_budget`
  failed before the fix because scheduling returned `None`, then passed.
- `cargo test -p r3akt-rch-server
  internal_delivery_attempt_clears_retry_scheduled_like_python_callback` failed
  before the retry-start cleanup because `retry_reason` remained present, then
  passed.
- `cargo test -p r3akt-rch-server propagated_broadcast` passed 7 focused
  propagated broadcast fallback tests.
- `cargo test -p r3akt-rch-server` passed.
- `cargo fmt --all -- --check` passed.
- `cargo clippy --workspace --all-targets -- -D warnings` passed.
- After restarting the fixed binary, live rows
  `dc8c20bc041b47f78c313f77eea916c1` and
  `991ee56574b04ca59c0a5bd173a4c5b0` moved from terminal failed back to
  `queued` / `in_progress` propagated fallback retry state.
- Final `/Chat/Messages?limit=500` verification for
  `2a2892b3227b427487308d53712dd163` returned `State=propagated`,
  `method=propagated`, `dispatch_status=accepted`, `reticulumd_dispatch_count=13`,
  and no serialized `error`, `retry_reason`, or
  `last_attempt_failed_at_ts_ms`.

Remaining retest:

- The live mesh is still hitting `SDK_SECURITY_RATE_LIMITED`, so phone/deck
  receipt remains blocked by the SDK/RNS rate-limit window. Continue stress
  until queued propagated fallbacks reach accepted/sent propagation on the two
  USB phones and embedded decks.

## 2026-06-23 Wrapped List UI Reconciliation

Trigger:

- The operator again saw message `2a2892b3227b427487308d53712dd163` as
  `failed` / `propagated` / `broadcast_direct_timeout_fallback` with
  `send_error`.

Live state:

- Direct SQLite inspection of `RTH_Store\rch_state.sqlite3` showed the reported
  row is still canonical `delivery_state=propagated`,
  `dispatch_status=accepted`, `attempts=5`.
- The active stress probe `2d437d80fbeb4c4cbc36c6fc3f9faeaa` remained
  non-terminal under the SDK/RNS rate-limit window, moving between queued and
  in-progress propagated fallback retries.

UI finding:

- Raw HTTP checks showed the current local server returns plain arrays for
  `/Events` and `/Chat/Messages`.
- The repeated visible card is therefore consistent with a stale browser tab or
  older loaded bundle, not the current backend row.
- The dashboard and chat stores were still hardened to accept both raw arrays
  and Python-style wrapped list responses so future compatibility envelopes
  cannot prevent authoritative refreshes from replacing stale in-memory state.

Fix:

- Added `ui/src/utils/api-list.ts` to unwrap raw arrays plus `value`, `Value`,
  `items`, and `Items` list envelopes.
- Updated the dashboard refresh path to unwrap wrapped `/Events`, mission, and
  team-member snapshots before replacing in-memory events.
- Updated the chat history refresh path to unwrap wrapped `/Chat/Messages`
  before mapping rows.

Verification:

- `npm --prefix ui run lint` passed.
- `npm --prefix ui run test -- dashboard chat` passed, including a regression
  where a wrapped `/Events` snapshot clears an older
  `message_delivery_failed` card for `2a2892b3227b427487308d53712dd163`.
- `npm --prefix ui run build` passed and the live server returned
  `200 text/html` serving rebuilt bundle `assets/index-kc7Jg-Vq.js`.
- In-app browser navigation to `http://127.0.0.1:18080/` timed out before
  rendered proof could be captured.

Remaining retest:

- Refresh or reload the manual browser tab so it loads the rebuilt bundle.
- Continue live delivery stress once the SDK/RNS rate-limit window clears and
  confirm propagated dispatch reaches accepted/sent state on the connected
  phones/decks.

## 2026-06-23 Packaging and Sidecar RC Smoke

Scope:

- Local Windows validation of the full server package assembly script and Tauri
  desktop sidecar preparation.
- CI matrix inspection only for macOS, Linux AMD64, Linux Raspberry Pi 64,
  Windows NSIS, and Linux AppImage.

Evidence:

- `scripts/build-rust-release-package.ps1` stages server binary, optional TAK
  service binary, packaging templates, Windows helper scripts, docs, optional
  `ui/dist`, `release-manifest.json`, an archive, and a `.sha256` sidecar.
- `.github/workflows/rust-release.yml` builds full server packages for Windows
  x64, macOS x64, macOS arm64, Linux AMD64, and Linux Raspberry Pi 64. It also
  builds desktop artifacts for Windows x64 NSIS and Linux x64 AppImage.
- `apps/rch-desktop/scripts/prepare-sidecar.mjs` prepares both
  `r3akt-rch-server` and `r3akt-tak-service` sidecar binaries with the host
  target triple suffix required by Tauri.

Local run:

- Ran `powershell -ExecutionPolicy Bypass -File
  scripts\build-rust-release-package.ps1 -PackageName
  codex-rch-rc-package-smoke -ReleaseVersion codex-rc-smoke-20260623
  -OutputDir target\rc-package-smoke -ServerBinaryPath
  target\release\r3akt-rch-server.exe -TakServiceBinaryPath
  target\release\r3akt-tak-service.exe -IncludeTakService -IncludeUi
  -ArchiveFormat zip`.
- Generated `target\rc-package-smoke\codex-rch-rc-package-smoke.zip`
  (`8,852,114` bytes) and a matching SHA-256 sidecar with hash
  `173AEC4E75AFC8975D2639A7941A1232008D5786E47B722B65E97EAE8500DA09`.
- Manifest recorded `includes_server=true`, `includes_tak_service=true`,
  `includes_ui=true`, and binaries `r3akt-rch-server.exe` plus
  `r3akt-tak-service.exe`.
- Archive entries included `bin\r3akt-rch-server.exe`,
  `bin\r3akt-tak-service.exe`, server and TAK service systemd templates,
  Windows start/install helpers, and `ui\index.html`.
- Ran `npm --prefix apps/rch-desktop run prepare:sidecar`; it prepared ignored
  Windows sidecars `r3akt-rch-server-x86_64-pc-windows-msvc.exe` and
  `r3akt-tak-service-x86_64-pc-windows-msvc.exe`.

Documentation fix:

- Updated `apps/rch-desktop/README.md` to say both sidecars are prepared and
  bundled, while the shell currently starts only the RCH server sidecar
  automatically.

Remaining release gate:

- This does not prove the hosted release workflow matrix. Run
  `Build Rust Release Packages` before publishing the RC and verify uploaded or
  attached artifacts plus checksums for all matrix entries.

## 2026-06-23 Release Gate and Main Merge

Context:

- PR #201 targeted `main`; after `origin/main` advanced to include PR #200,
  GitHub reported no checks and `mergeStateStatus=DIRTY`.
- A non-mutating merge preview showed one conflict in
  `crates/r3akt-rch-server/src/lib.rs` around broadcast fallback retry
  scheduling.

Resolution:

- Merged `origin/main`.
- Preserved this branch's retryable propagated fallback behavior and retained
  `main`'s local-transport retry helper in the retry scheduler predicate.
- Removed the duplicate broadcast-only timeout propagation path from `main` in
  favor of this branch's generalized broadcast/fanout direct-timeout propagation
  path, with the metadata cleanup and `direct_attempts` field folded in.

Verification:

- `cargo test -p r3akt-rch-server propagated_broadcast` passed 10 focused
  propagated broadcast fallback tests.
- `cargo fmt --all -- --check` passed.
- `scripts\release-readiness.ps1 -ServerOnlyAlpha -SkipClippy
  -SkipWorkspaceTests -Bind 127.0.0.1:18082 -ApiKey codex-release-gate
  -LxmfZmqCommand tcp://localhost:9100 -LxmfZmqResponse
  tcp://localhost:9101 -ReticulumdSource codex-release-gate` passed.

Runtime note:

- The first post-merge release gate attempt failed because the manual
  DB/config-backed server was running from `target\release\r3akt-rch-server.exe`
  and Windows denied Cargo replacing the locked binary.
- Stopped the manual server briefly, reran the gate, and restarted the manual
  server on `http://127.0.0.1:18080/` with PID `26344`, using
  `RTH_Store\rch_state.sqlite3`, `RTH_Store\config.ini`, API key
  `manual-test`, Reticulum RPC `127.0.0.1:14243`, and LXMF ZMQ endpoints
  `tcp://127.0.0.1:19100` / `tcp://127.0.0.1:19101`.

Remaining release gate:

- Push the merge and wait for GitHub to report checks for PR #201.
- Full clippy/workspace tests were not rerun in this local gate; rely on
  GitHub PR quality checks or run them locally before marking the PR ready.
