# RCH Rust Packaging

Rust has two package shapes:

- Server package: deployable `r3akt-rch-server` binary plus UI bundle, config
  templates, service helper files, and checksums.
- TAK service package contents: deployable `r3akt-tak-service` companion binary
  plus its own service helper files. It is a separate process that talks to RCH
  through the northbound HTTP API and talks to TAK through `COT_URL`.
- Desktop package: Tauri shell that bundles the shared UI and launches
  `r3akt-rch-server` as a managed local sidecar. The TAK service binary is
  bundled as a separate sidecar artifact for operator-managed startup.

Python 2.9.x packaging remains on `rch-python` and keeps using the existing
Electron wrapper.

## Release Lines

- Python maintenance: `v2.9.x` from `rch-python`.
- Rust previews: `v3.0.0-preview.N` from `rust-next`.
- Rust stable: `v3.0.0` after all Rust server and desktop gates pass.
