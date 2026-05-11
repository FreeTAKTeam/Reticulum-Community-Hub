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

Validated during the root Rust import and refreshed on 2026-05-11:

- `cargo fmt --all -- --check`: passed.
- `cargo clippy --workspace --all-targets -- -D warnings`: passed.
- `cargo test -p r3akt-rch-core`: passed.
- `cargo test -p r3akt-transport-rns`: passed.
- `cargo test -p r3akt-tak-connector`: passed.
- `cargo test -p r3akt-rch-server`: passed, including the server library,
  gateway binary, `release_major_functionality`, and SAR HTTP seeder suites.
- `cargo test --workspace`: passed across all Rust crates and examples.
- `cargo build --release -p r3akt-rch-server`: passed for the deployable
  server binary.
- Release-binary smoke test with a temporary SQLite database: passed for
  `/Status`, `/openapi.json`, `/Help`, `/api/v1/app/info`, topic creation/list,
  chat creation/list, checklist template creation, mission creation/list, and
  offline checklist creation/list.
- Live smoke test with a temporary SQLite database: passed for `/openapi.json`,
  `/Help`, `/api/v1/app/info`, authenticated `/Status`, topic creation, chat
  message creation, checklist template creation, mission creation, and offline
  checklist creation.

Release blockers cleared in the latest parity pass:

- `r3akt-rch-server` tests no longer hang in mission fanout coverage; the fake
  Reticulum RPC helper now reads one HTTP request frame instead of waiting for
  connection close.
- Voice-capable LXMF destinations remain chat destinations. Voice is treated as
  an additional feature on top of LXMF chat, not as a separate voice-only
  routing class.
- Inbound reticulumd worker tests now cover the current event poll,
  `list_messages`, and announce poll order deterministically.
- Direct-send tests now assert the LXMF-rs SDK RPC methods and SDK-prefixed
  receipt identifiers used by the Rust adapter.

## Known Parity Boundaries

The Rust edition preserves the RCH northbound contract as the compatibility
target. Remaining external validation should be tracked explicitly, especially
live multi-node LXMF receipt behavior, live TAK reconnect/inbound behavior
against a real TAK profile, and live multi-recipient fanout validation.
