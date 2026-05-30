# RCH Rust Packaging

The Rust packaging line now has two release package shapes:

- Server package: deployable `r3akt-rch-server` binary, `r3akt-tak-service`
  binary, mandatory ZeroMQ southbound configuration, shared UI bundle, service
  helper files, config templates, and checksums.
- Desktop packages: Tauri bundles from `apps/rch-desktop` with the Rust server
  and TAK service sidecars. Current CI builds Windows x64 NSIS and Linux x64
  AppImage artifacts.

Python 2.9.x packaging remains on `rch-python` and keeps using the existing
Electron wrapper.

The server-only alpha gate remains `scripts/release-readiness.ps1
-ServerOnlyAlpha`. Full release packaging is handled by
`.github/workflows/rust-release.yml`, which mirrors the Python release workflow
shape: manual workflow artifacts on `workflow_dispatch` and file attachment
when a GitHub release is published. Server package names include the resolved
release version, for example
`rch-rust-full-windows-x64-v3.0.0-preview.0.zip`; the same version, Git ref,
and commit SHA are written into `release-manifest.json` inside the archive.
Manual workflow runs default to `v3.0.0-preview.0` and can override that label
with the `release_version` input.

Pull request quality control is handled by
`.github/workflows/rust-pr-quality.yml`. It runs Rust 1.85 formatting, clippy,
locked workspace tests, release builds for the server and TAK service, and
`cargo audit` before release packaging is considered.

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
- Rust alpha previews: `v3.0.0-alpha.N` or `v3.0.0-preview.N` from
  `rust-next`, with server package artifacts and optional desktop artifacts.
- Rust stable: `v3.0.0` after all Rust server and desktop gates pass.
