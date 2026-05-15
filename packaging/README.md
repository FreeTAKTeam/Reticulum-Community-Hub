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

## Python Store Migration

Rust packages can be installed over an existing Python RCH data directory by
running the migration wrapper before the Rust server starts:

```powershell
scripts\migrate-python-rch.ps1 -SourceStore RCH_Store -TargetDataDir RTH_Store
```

The wrapper copies `config.ini`, `identity`, `telemetry.db`, files, images, and
LXMF runtime data, then converts `rth_api.sqlite` into the Rust
`rch_state.sqlite3` snapshot database. The Rust converter is available as:

```powershell
cargo run -p r3akt-rch-core --bin migrate_python_rch -- --legacy-db RCH_Store\rth_api.sqlite --target-db RTH_Store\rch_state.sqlite3 --legacy-config RCH_Store\config.ini
```

The runtime can also prompt for this import on first start:

```powershell
r3akt-rch-server start --data-dir RTH_Store --prompt-python-import
```

With `--prompt-python-import`, Rust only prompts when `rch_state.sqlite3` is
new or empty. It checks the runtime `config.ini`, `[migration]` keys such as
`python_store` or `python_db`, and nearby `RCH_Store`/`RTH_Store` directories.
If no legacy store is found, it asks for the Python store directory or
`rth_api.sqlite` path.

## Release Lines

- Python maintenance: `v2.9.x` from `rch-python`.
- Rust previews: `v3.0.0-preview.N` from `rust-next`.
- Rust stable: `v3.0.0` after all Rust server and desktop gates pass.
