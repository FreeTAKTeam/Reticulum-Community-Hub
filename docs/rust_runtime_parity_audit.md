# Rust Runtime Parity Audit

Last verified: 2026-05-03

## Objective

Full parity for this work means the same RCH behavioral tests can be run against
the Python implementation and the Rust implementation, and both pass.

## Current Evidence

- Full Python suite:
  - Command: `.\.venv\Scripts\python.exe -m pytest --no-cov -q`
  - Result: `858 passed, 385 warnings`
- Shared Python-vs-Rust southbound runtime suite:
  - File: `tests/rust_runtime/test_rch_bridge_parity.py`
  - Command inventory guard covers all declared mission/checklist southbound
    commands from:
    - `reticulum_telemetry_hub.mission_sync.capabilities.MISSION_COMMAND_CAPABILITIES`
    - `reticulum_telemetry_hub.checklist_sync.capabilities.CHECKLIST_COMMAND_CAPABILITIES`
  - Current command coverage: `85 / 85`
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
  create/update/delete route flow parameterized across Python and Rust
- zone create/list/patch/delete
- FastAPI northbound zone create/list/update/delete route flow
  parameterized across Python and Rust
- FastAPI northbound EAM authenticated CRUD route flow parameterized across
  Python storage and a Rust bridge-backed EAM service/domain adapter
- marker and zone state observed through Rust bridge snapshot requests,
  matching Python service state in the shared parity harness
- checklist/template/task/cell/feed state observed through the Rust bridge
  `state_snapshot` request instead of direct SQLite table decoding
- FastAPI northbound topic CRUD/subscribe route flow parameterized across
  Python storage and a Rust bridge-backed API adapter, including topic and
  subscriber pagination route checks
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
- mission and checklist source-identity mismatch rejection at the transport
  bridge boundary
- unauthorized, unknown command, invalid payload, and not-found rejection shapes

## Remaining Gap To Full-Suite Parity

The full collected Python suite is broader than the Rust runtime bridge. It also
tests Python-specific or not-yet-Rust-backed surfaces including:

- FastAPI northbound routes beyond the current topic, marker, zone, and EAM
  Rust-backed flows, plus OpenAPI contracts
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
