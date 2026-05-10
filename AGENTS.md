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
