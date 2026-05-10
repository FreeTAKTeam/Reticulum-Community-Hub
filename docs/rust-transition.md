# RCH Rust Transition

`rust-next` is the staged Rust edition of Reticulum Community Hub. The Python
implementation at release `2.9.6` is preserved on `rch-python` for long-term
maintenance.

## Branches

- `rch-python`: Python RCH maintenance branch created from `main` at
  `a520574ecbc243841a1a215b616b6792452de2a1`.
- `rust-next`: Rust R3AKT/RCH workspace imported as the repository root.
- `ui-shared`: canonical Vue web UI source shared by Python maintenance and
  Rust product work.
- `main`: remains the GitHub default branch until Rust release gates pass and
  the default branch is switched deliberately.

## Rust Public Surface

- `r3akt-rch-server`: UI-facing and northbound backend replacement.
- `r3akt-rch-core`: RCH domain model, persistence, mission/checklist/topic
  behavior, and Python-compatible response shaping.
- `r3akt-transport-rns`: LXMF-rs and `reticulumd` adapter boundary.
- `r3akt-tak-connector`: separately deployable TAK connector service boundary.

## Release Gates

Before switching the GitHub default branch to Rust, the branch must pass:

```powershell
cargo fmt --all -- --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
cargo test -p r3akt-rch-server
cargo test -p r3akt-rch-core
cargo test -p r3akt-transport-rns
cargo test -p r3akt-tak-connector
```

The live smoke test should start `r3akt-rch-server` with a temporary SQLite
database and validate `/Status`, `/openapi.json`, `/Help`, `/api/v1/app/info`,
and at least one topic/chat/checklist/mission flow.

## Packaging

- Server packages are built from `r3akt-rch-server` and include the built
  `ui/dist`, config samples, a Linux `systemd` unit, Windows PowerShell helpers,
  and checksums.
- Desktop packages are built from `apps/rch-desktop` with Tauri. The app loads
  the shared Vue UI and starts `r3akt-rch-server` as a managed sidecar on
  `127.0.0.1:8000`.
- Windows and Linux are the first-class Rust packaging targets. Windows produces
  a Tauri NSIS installer and server archive; Linux produces a Tauri AppImage and
  server tarball.
- Python `2.9.x` keeps its existing Electron package on `rch-python`; Electron
  is not part of `rust-next`.

## Current Validation Snapshot

Validated during the root Rust import:

- `cargo fmt --all -- --check`: passed.
- `cargo clippy --workspace --all-targets -- -D warnings`: passed.
- `cargo test -p r3akt-rch-core`: passed.
- `cargo test -p r3akt-transport-rns`: passed.
- `cargo test -p r3akt-tak-connector`: passed.
- `cargo test -p r3akt-rch-server --test release_major_functionality`: passed,
  including the major functionality release test suite.
- Live smoke test with a temporary SQLite database: passed for `/openapi.json`,
  `/Help`, `/api/v1/app/info`, authenticated `/Status`, topic creation, chat
  message creation, checklist template creation, mission creation, and offline
  checklist creation.

Release blockers remaining:

- `cargo test --workspace` and `cargo test -p r3akt-rch-server` are not
  release-clean yet because the `r3akt-rch-server` lib test binary hangs on
  `tests::mission_change_listener_fans_out_to_mission_team_recipients`.
- The same server lib run also exposes order-dependent failures around client
  announce metadata and direct routing expectations:
  `client_route_lists_persisted_clients_with_python_shape`,
  `direct_reticulumd_failure_cools_down_next_targeted_send_to_propagated`,
  `internal_identity_announce_records_presence_and_rem_metadata`,
  `marker_fanout_skips_stale_rem_and_dedupes_generic_peer_names`, and
  `message_route_uses_direct_reticulumd_send_for_live_present_target`.

## Known Parity Boundaries

The Rust edition preserves the RCH northbound contract as the compatibility
target. Remaining work should be tracked as explicit parity gaps, especially
live LXMF receipt behavior, live TAK reconnect validation, inbound TAK behavior
where required, and live multi-recipient fanout validation.
