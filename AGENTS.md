# AGENTS.md - RCH Rust Edition

This branch is the Rust transition branch for Reticulum Community Hub. The
Python implementation is preserved on `rch-python`; do not reintroduce Python,
Vue, or Electron source into `rust-next` unless the user explicitly asks for a
compatibility artifact.

## Project Shape

- Workspace root: `Cargo.toml`
- Main server crate: `crates/r3akt-rch-server`
- RCH domain/state crate: `crates/r3akt-rch-core`
- LXMF/Reticulum adapter crate: `crates/r3akt-transport-rns`
- TAK service boundary: `crates/r3akt-tak-connector`
- Rust edition: 2024
- Minimum Rust version: 1.85
- License: EPL-2.0

This workspace currently depends on the LXMF Rust workspace as a sibling
checkout named `LXMF-rs`.

Expected local layout:

```text
src/
├── Reticulum-Community-Hub/   # this repository
└── LXMF-rs/                   # dependency for lxmf-wire
```

## UI and Packaging

- `ui/` is imported from the canonical `ui-shared` branch and must stay
  compatible with both Python RCH 2.9.x and Rust `r3akt-rch-server`.
- `apps/rch-desktop/` is the Tauri desktop shell for the Rust product line.
- `packaging/` contains server package templates and install helpers.
- Keep Electron only on `rch-python`; do not reintroduce Electron packaging on
  `rust-next`.
- Rust server packages are the deployment primitive. Tauri is a desktop shell
  for local operator workstations.

## Required Checks

Run these before declaring Rust transition work complete:

```powershell
cargo fmt --all -- --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
```

For release-critical backend work, also run:

```powershell
cargo test -p r3akt-rch-server
cargo test -p r3akt-rch-core
cargo test -p r3akt-transport-rns
cargo test -p r3akt-tak-connector
```

For shared UI changes, also run:

```powershell
npm --prefix ui ci
npm --prefix ui run lint
npm --prefix ui run test
npm --prefix ui run build
```

For Rust package changes, run the relevant package build:

```powershell
cargo build --release -p r3akt-rch-server
npm --prefix apps/rch-desktop install
npm --prefix apps/rch-desktop run build
```

## Operational Workflows

- Use `.\scripts\release-readiness.ps1 -ServerOnlyAlpha` as the local
  server-only release gate. Use `-LiveTak -LiveReticulum` only when the
  required live infrastructure is configured and reachable.
- When the sibling `LXMF-rs\target\debug\reticulumd.exe` is available, use
  `.\scripts\local-reticulum-live-gate.ps1 -IncludeZmqEventPoll` for
  local receipt, fanout, and ZeroMQ event-poll validation. Add
  `-IncludeZmqLoad` or `-ZmqLoadOnly` for the local ZeroMQ load gate.
- The Rust PR quality workflow runs locked dependency fetches, release builds
  for the RCH server and TAK service, and `cargo audit --deny warnings`.
- The desktop release path builds the Tauri shell after
  `npm --prefix apps/rch-desktop ci`; its sidecar preparation produces the
  release RCH server and TAK-service binaries for `apps/rch-desktop`.

For server release-candidate work, use the committed gate runner before
claiming release readiness:

```powershell
.\scripts\release-readiness.ps1 -ServerOnlyAlpha
```

Use `scripts/local-reticulum-live-gate.ps1` for explicit local Reticulum
receipt/fanout/ZeroMQ event-poll or load validation when the sibling
`LXMF-rs\target\debug\reticulumd.exe` is available. Add `-LiveTak` or
`-LiveReticulum` to release-readiness only when the required external
infrastructure and environment variables are configured.

## Local Runtime Workflow

- A Rust server launch that must exercise southbound Reticulum/LXMF behavior is
  not complete with HTTP alone. Run `r3akt-rch-server` with LXMF-rs ZeroMQ SDK
  endpoints and a `reticulumd` source, or let it manage a sibling
  `LXMF-rs` `reticulumd.exe` built with `zmq-pipeline-rpc` support.
- Verify local runtime work with `/Status` plus `/diagnostics/runtime`; for
  daemon-backed runs, diagnostics should show Reticulum/`reticulumd`
  configured and running.
- Keep the local launch commands in `README.md` as the source of truth for
  `--lxmf-zmq-command`, `--lxmf-zmq-response`, `--reticulumd-source`,
  `--reticulumd-exe`, and UI bundle flags.

## Diagnostics and Error Handling

- Follow the spirit of LXMF-rs issue #369 for RCH transport, TAK, migration,
  and runtime paths: do not hide unexpected errors behind `.ok()`, `let _ =`,
  or `unwrap_or_default()` when the caller or operator needs to distinguish
  absent data from malformed data, dropped work, encode/decode failure, or a
  poisoned lock.
- Prefer propagating `Result` with context, or logging at `warn!`/`error!`
  before intentionally discarding a failure. This is especially important for
  MessagePack/JSON/XML parsing, UTF-8 conversion, channel sends, socket writes,
  worker lifecycle transitions, delivery receipts, and reticulumd/TAK bridge
  calls.
- It is still acceptable to ignore best-effort cleanup failures in tests or
  shutdown code, but production paths should expose enough context through
  logs, events, delivery metadata, or `/diagnostics/runtime` for an operator to
  debug the failure without tracing every call site manually.

## Release Packaging Workflow

- `.github/workflows/rust-release.yml` owns published Rust release packages.
  Keep release workflow changes aligned with `docs/rust-transition.md`,
  `packaging/README.md`, and `docs/release-readiness-audit.md`.
- Current server archives are built for Windows x64, macOS x64, macOS arm64,
  Linux AMD64, and Linux Raspberry Pi 64; do not create duplicate packaging
  workflows for the same release surface.
- Python 2.9.x packaging remains on `rch-python`; keep Rust release-package
  changes in the Rust packaging path unless the user explicitly asks for a
  Python compatibility artifact.

## Compatibility Rules

- Preserve the RCH northbound contract as the compatibility target: `/Status`,
  `/Help`, `/Examples`, OpenAPI, REST route families, WebSocket streams, R3AKT
  mission/checklist APIs, file/image/topic/subscriber/client routes, and auth
  behavior.
- Keep Python parity gaps documented in `README.md` or `docs/rust-transition.md`.
- Keep runtime artifacts untracked: `target/`, SQLite DBs, logs, screenshots,
  `.playwright-mcp/`, and generated local files.
- Do not mutate `rch-python` from this branch. Python maintenance belongs on
  the `rch-python` branch.

## Documentation References

- `docs/rust-transition.md` - Branch roles, migration status, and Rust surface
- `docs/rem-southbound-interface.md` - Rust-side REM southbound contract notes
