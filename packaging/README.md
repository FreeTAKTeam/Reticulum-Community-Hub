# RCH Rust Packaging

Rust has two package shapes:

- Server package: deployable `r3akt-rch-server` binary plus UI bundle, config
  templates, service helper files, and checksums.
- Desktop package: Tauri shell that bundles the shared UI and launches
  `r3akt-rch-server` as a managed local sidecar.

Python 2.9.x packaging remains on `rch-python` and keeps using the existing
Electron wrapper.

## Release Lines

- Python maintenance: `v2.9.x` from `rch-python`.
- Rust previews: `v3.0.0-preview.N` from `rust-next`.
- Rust stable: `v3.0.0` after all Rust server and desktop gates pass.
