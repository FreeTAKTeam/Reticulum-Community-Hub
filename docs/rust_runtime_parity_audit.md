# Rust Runtime Parity Audit

Last verified: 2026-05-03

## Objective

Full parity for this work means the same RCH behavioral tests can be run against
the Python implementation and the Rust implementation, and both pass.

## Current Evidence

- Full Python suite:
  - Command: `.\.venv\Scripts\python.exe -m pytest --no-cov -q`
  - Result: `894 passed, 465 warnings`
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
- marker and zone state observed through Rust bridge snapshot requests,
  matching Python service state in the shared parity harness
- checklist/template/task/cell/feed state observed through the Rust bridge
  `state_snapshot` request instead of direct SQLite table decoding
- FastAPI northbound topic CRUD/subscribe route flow parameterized across
  Python storage and a Rust bridge-backed API adapter, including topic and
  subscriber pagination route checks, subscriber CRUD, and topic pagination
  after config reload
- Direct `ReticulumTelemetryHubAPI` topic CRUD, topic description clearing,
  topic missing/error behavior, topic patch-without-updates behavior, subscriber
  CRUD, subscriber missing/error behavior, subscriber destination validation,
  and title-case subscriber metadata patch tests, subscriber `reject_tests`
  create/patch-zero behavior, plus client join/list/leave, blank join/leave
  identity rejection, and identity capability grant/list/revoke behavior,
  plus topic/client/identity-announce persistence, missing-name announce
  preservation, and bulk display-name resolution, parameterized across Python
  storage and a minimal Rust bridge-backed
  topic/subscriber/client/API-rights/identity adapter
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
- mission and checklist source-identity mismatch rejection at the transport
  bridge boundary
- unauthorized, unknown command, invalid payload, and not-found rejection shapes

## Remaining Gap To Full-Suite Parity

The full collected Python suite is broader than the Rust runtime bridge. It also
tests Python-specific or not-yet-Rust-backed surfaces including:

- FastAPI northbound routes beyond the current topic, marker, zone, EAM,
  R3AKT core registry, full registry matrix, assignment/skill registry,
  mission-list-limit, and mission-change/log Rust-backed flows, plus OpenAPI
  contracts
- Direct `ReticulumTelemetryHubAPI` tests beyond current topic/subscriber CRUD,
  client, identity-capability, and basic identity-announce parity, including
  attachment association, identity status/moderation, REM peer registry,
  subject-rights storage, config, and app-info behavior
- CLI process-control behavior
- Python storage/migration helpers
- Reticulum daemon lifecycle and outbound queue behavior
- telemetry sampling and serialization
- gateway runtime/control wiring
- file/image route behavior
- auth helpers and config editing behavior
- internal API bus/query/event abstractions
- documentation conformance tests

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
