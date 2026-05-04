# Rust Runtime Parity Audit

Last verified: 2026-05-04

## Objective

Full parity for this work means the same RCH behavioral tests can be run against
the Python implementation and the Rust implementation, and both pass.

## Current Evidence

- Full Python suite:
  - Command: `.\.venv\Scripts\python.exe -m pytest --no-cov -q`
  - Result: `1026 passed, 690 warnings`
- Shared Python-vs-Rust southbound runtime suite:
  - File: `tests/rust_runtime/test_rch_bridge_parity.py`
  - Command inventory guard covers all declared mission/checklist southbound
    commands from:
    - `reticulum_telemetry_hub.mission_sync.capabilities.MISSION_COMMAND_CAPABILITIES`
    - `reticulum_telemetry_hub.checklist_sync.capabilities.CHECKLIST_COMMAND_CAPABILITIES`
  - Current command coverage: `87 / 87`
  - Current shared backend result: `33 passed`
- Rust workspace:
  - Command: `cargo test --workspace`
  - Result: passed
  - Command: `cargo clippy --workspace --all-targets -- -D warnings`
  - Result: passed

## What Is Covered By Shared Python-vs-Rust Tests

The shared parity harness currently executes the same assertions against:

- `PythonRchBackend`, using the Python mission/checklist routers and domain services.
- `RustRchBackend`, using `r3akt-rch-bridge` and Rust SQLite state.

It covers:

- mission lifecycle: join, message send, event list, leave
- topic create/list/patch/subscribe/delete
- topic subscriber state observed through the Rust bridge `list_subscribers`
  request, matching Python API subscriber state in the shared parity harness
- marker create/list/patch
- marker rename/delete southbound commands and the FastAPI marker
  create/update/delete route flow, MDI symbol acceptance, and alias
  normalization parameterized across Python and Rust
- FastAPI marker symbol inventory and marker telemetry persistence without a
  dispatcher parameterized across Python storage and the Rust bridge
- zone create/list/patch/delete
- mission marker link/unlink southbound commands, with marker link state
  persisted in Rust and exposed through mission registry route parity
- FastAPI northbound zone create/list/update/delete route flow and invalid
  self-intersecting geometry rejection parameterized across Python and Rust
- FastAPI northbound EAM authenticated CRUD, canonical auto-provisioning,
  legacy field rejection, expired snapshot filtering, recreate-after-delete,
  and team-summary route flows parameterized across Python storage and a Rust
  bridge-backed EAM service/domain adapter
- FastAPI northbound R3AKT mission list limit route flow parameterized across
  Python storage and a Rust bridge-backed mission domain adapter
- FastAPI northbound R3AKT core mission, parent, RDE, team, team-member,
  mission-marker link/list/unlink, member-client, asset, and skill route flow
  parameterized across Python storage and a Rust bridge-backed mission domain
  adapter
- FastAPI northbound R3AKT team-member-skill, task-skill-requirement,
  assignment, and assignment-asset route flow parameterized across Python
  storage and a Rust bridge-backed mission domain adapter
- FastAPI northbound full R3AKT registry route matrix parameterized across
  Python storage and a Rust bridge-backed mission/domain/API adapter, including
  capability grant/revoke, mission CRUD/patch/parent/RDE, mission-zone and
  mission-marker links, mission changes, log entries, teams, team members,
  mission rights subjects/access, assets, skills, checklist task references,
  assignments, expansion payloads, cleanup flows, events, and snapshots
- FastAPI northbound R3AKT mission-change and log-entry route flow
  parameterized across Python storage and a Rust bridge-backed mission domain
  adapter
- FastAPI core route smoke path parameterized across Python storage and the
  Rust bridge, including mission/checklist route creation through the selected
  backend, Rust-backed client/identity/config facade behavior, and Rust-backed
  subject operation-right grants
- FastAPI legacy client list and paginated client response parameterized across
  Python storage and Rust-backed client join/list state
- FastAPI hub/Reticulum config rejection routes and identity moderation routes
  parameterized across Python storage and the Rust-backed facade
- FastAPI event-log route and Reticulum runtime fallback routes parameterized
  across Python storage and the Rust-backed facade
- Internal API adapter topic, subscriber, node-status, message, and event-stream
  routes parameterized across Python storage and the Rust-backed facade
- marker and zone state observed through Rust bridge snapshot requests,
  matching Python service state in the shared parity harness
- checklist/template/task/cell/feed state observed through the Rust bridge
  `state_snapshot` request instead of direct SQLite table decoding
- FastAPI northbound topic CRUD/subscribe route flow parameterized across
  Python storage and a Rust bridge-backed API adapter, including topic and
  subscriber pagination route checks, subscriber CRUD, and topic pagination
  after config reload, remote-auth enforcement, and missing-ID patch validation
- Direct `ReticulumTelemetryHubAPI` topic CRUD, topic description clearing,
  topic missing/error behavior, topic patch-without-updates behavior, subscriber
  CRUD, subscriber missing/error behavior, subscriber destination validation,
  and title-case subscriber metadata patch tests, subscriber `reject_tests`
  create/patch-zero behavior, plus client join/list/leave, blank join/leave
  identity rejection, and identity capability grant/list/revoke behavior,
  plus topic/client/identity-announce persistence, missing-name announce
  preservation, and bulk display-name resolution, parameterized across Python
  storage and identity status ban/blackhole/list behavior through a minimal
  Rust bridge-backed
  topic/subscriber/client/API-rights/identity/REM adapter, including REM
  capability classification, REM mode persistence, connected-mode detection,
  peer registry shaping, generic-client mode suppression, and destination plus
  identity announce merge behavior; case-insensitive identity status dedupe for
  joined and announce-only identities, plus blackhole-preserving moderation
  dedupe, display-name duplicate collapse, joined-identity preference, and
  concurrent client join/leave plus identity announce upsert dedupe behavior,
  topic patch created-timestamp preservation, attachment metadata topic
  assignment/clearing, topic-delete attachment association cleanup, legacy raw
  UUID attachment cleanup, and case-distinct attachment preservation behavior,
  app-info/Reticulum destination validation behavior, plus static
  subject-rights operation definition inventory and config apply/rollback
  validation behavior; subject-rights capability-grant listing,
  mission-access role effective authorization, and explicit operation revoke
  override behavior are also parameterized across Python and Rust
- mission registry CRUD, patch, parent, zone link/unlink, RDE
- mission change and log entry upsert/list
- team, team member, client link/unlink, asset, skill, assignment, and assignment asset flows
- EAM upsert/list/get/latest/summary/delete, including canonical team validation,
  member/team mismatch rejection, active callsign conflict rejection, and
  mission-scoped status-write authorization
- checklist create/get/list/join/upload/feed/delete
- checklist template create/list/get/update/clone/delete
- checklist task row add/delete/style/status/cell set
- checklist CSV import
- checklist read authorization through mission-scoped team-member roles and
  linked client identities
- FastAPI northbound checklist template, checklist lifecycle, task row, task
  status/style/cell, upload/feed, delete, and CSV import route matrix
  parameterized across Python storage and the Rust bridge-backed domain adapter
- FastAPI northbound file/image metadata list, pagination, retrieve, topic
  patch, raw-byte retrieval, delete, missing-record, and remote-auth route
  behavior parameterized across Python storage and the Rust bridge-backed API
  adapter; legacy direct-SQLAlchemy image path deletion remains Python-only
- Direct file/image API store, list, retrieve, delete, category rejection,
  missing-record, missing-path, and outside-storage validation behavior
  parameterized across Python storage and the Rust bridge-backed API adapter;
  Python filesystem monkeypatch deletion tolerance remains Python-only
- LXMF command-manager file/image list, retrieve, missing-field,
  missing-record, camel-case ID, and missing-on-disk behaviors parameterized
  across Python storage and the Rust bridge-backed API adapter; explicit
  injected Python API exception logging remains Python-only
- Core command-manager app-info reply context, file/image list, file/image
  attachment retrieval, and invalid file ID behavior parameterized across
  Python storage and the Rust bridge-backed API adapter
- Core command-manager topic listing, topic creation, source-identity
  subscription, and zero-reject subscription behavior parameterized across
  Python storage and the Rust bridge-backed API adapter
- Standalone command-manager subscriber create/retrieve behavior parameterized
  across Python storage and the Rust bridge-backed API adapter
- Core command-manager help reply renderer hint behavior parameterized across
  Python storage and the Rust bridge-backed API adapter
- LXMF telemetry request topic filtering, unsubscribed-sender denial, and
  unknown-topic empty snapshot behavior parameterized across Python storage and
  the Rust bridge-backed API adapter
- Northbound service status snapshots, runtime diagnostics passthrough, routing
  fallback/provider behavior, API-backed topic/subscriber lookup helpers,
  telemetry status counts, file/image status counts, and app-info round trip
  behavior, plus help/examples fallback, event recording/listing, message
  dispatch validation, telemetry proxying, and Reticulum discovery/capability
  proxy behavior parameterized across Python storage and the Rust bridge-backed
  API adapter
- Northbound telemetry entry latest/collapse, topic filtering, and unknown-topic
  behavior parameterized across Python storage and the Rust bridge-backed API
  adapter; SQLAlchemy query-count optimization remains Python-only
- Northbound websocket telemetry broadcaster topic-subscription and
  destination-filter behavior parameterized across Python storage and the Rust
  bridge-backed API adapter
- FastAPI northbound status counts, subscribe destination validation, protected
  endpoint auth, auth validation, and bearer-token app/auth payload behavior
  parameterized across Python storage and the Rust bridge-backed API adapter
- FastAPI northbound sensitive core route remote-auth rejection behavior
  parameterized across Python storage and the Rust bridge-backed API adapter
- FastAPI northbound app-info configured hub display-name behavior
  parameterized across Python storage and the Rust bridge-backed API adapter
- FastAPI northbound chat message send, scope handling, and missing-dispatcher
  rejection behavior, plus configured attachment upload size-limit behavior,
  parameterized across Python storage and the Rust bridge-backed API adapter
- Direct chat message persistence, state update, stats, and uploaded attachment
  metadata behavior parameterized across Python storage and the Rust
  bridge-backed API adapter
- FastAPI northbound gateway control status/start/stop/sync and
  disabled-control 404 behavior parameterized across Python storage and the
  Rust bridge-backed API adapter
- Gateway app state, mission-domain-service handoff, and routing snapshot
  display-name behavior parameterized across Python storage and the Rust
  bridge-backed API adapter
- mission and checklist source-identity mismatch rejection at the transport
  bridge boundary
- unauthorized, unknown command, invalid payload, and not-found rejection shapes

## Remaining Gap To Full-Suite Parity

The full collected Python suite is broader than the Rust runtime bridge. It also
tests Python-specific or not-yet-Rust-backed surfaces including:

- Static OpenAPI contract checks and route-schema documentation conformance.
- Direct `ReticulumTelemetryHubAPI` private Python storage edge cases, including
  SQLAlchemy session retry and monkeypatched storage-return handling.
- CLI process-control behavior
- Python storage/migration helpers
- Reticulum daemon lifecycle and outbound queue behavior
- telemetry sampling, serialization, and SQL query-count optimization checks
- gateway runtime process boot/main-loop behavior
- file/image legacy direct-SQLAlchemy deletion paths outside the API abstraction
- auth helpers and config editing behavior
- low-level mission/checklist router unit tests that target Python services
  directly; the shared Rust bridge parity suite covers their command behavior
  through the bridge, but these Python-unit tests are not themselves backend
  selectable.

Those tests do not currently have a Rust backend selector. Passing the shared
southbound parity suite is therefore necessary evidence for the hot message path,
but it is not the same as running the entire Python test suite against Rust.

## Completion Criteria Still Missing

To mark full parity complete, one of these must exist and pass:

1. A Rust-backed test mode for the existing full Python suite, where the same
   tests can run with Python or Rust as the backend implementation.
2. A formally reduced full-parity suite definition accepted as the scope for the
   Rust runtime, with all selected tests parameterized across Python and Rust.

Until then, the current state is best described as full southbound command parity
coverage for the shared RCH runtime path, not full RCH application parity.

## Completion Audit Checklist

| Requirement | Current evidence | Status |
| --- | --- | --- |
| Same suite can run against Python backend | `.\.venv\Scripts\python.exe -m pytest --no-cov -q` passes with `1026 passed, 690 warnings` | Done for Python |
| Same suite can run against Rust backend | Many runtime-facing tests are parameterized with `backend in ["python", "rust"]`, but there is no global Rust backend mode for the full suite | Missing |
| Rust southbound command behavior matches Python | `tests/rust_runtime/test_rch_bridge_parity.py` covers `87 / 87` declared mission/checklist commands and passes | Done for scoped southbound path |
| Northbound API/runtime surfaces use Rust bridge where practical | Topic, subscriber, client, identity, REM, subject-rights, file/image, chat, telemetry, gateway, service, websocket, EAM, marker, zone, checklist, and R3AKT route slices are parameterized | Partial |
| Python-only application internals are either ported or formally excluded | Remaining Python-specific surfaces are listed above, but no accepted reduced full-parity scope exists | Missing |
| Completion can be marked | Requires a passing full Rust backend suite or an accepted reduced parity suite | Not complete |
