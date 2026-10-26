# RCH Rust Packaging

The Rust packaging line now has two release package shapes:

- Server package: deployable `r3akt-rch-server` binary, `r3akt-tak-service`
  binary, checksum-recorded LXMF `0.15.0` `reticulumd` binary with ZeroMQ
  support, mandatory ZeroMQ southbound configuration, shared UI bundle, service
  helper files, config templates, and checksums. Current release CI builds
  Windows x64, macOS x64, macOS arm64, Linux AMD64, and Linux Raspberry Pi 64
  server archives.
- Desktop packages: Tauri bundles from `apps/rch-desktop` with `reticulumd`,
  the Rust server, and TAK service sidecars. Current CI builds Windows x64 NSIS and Linux x64
  AppImage artifacts.

Python 2.9.x packaging remains on `rch-python` and keeps using the existing
Electron wrapper.

The server-only alpha gate remains `scripts/release-readiness.ps1
-ServerOnlyAlpha`. Full release packaging is handled by
`.github/workflows/rust-release.yml`, which mirrors the Python release workflow
shape: manual workflow artifacts on `workflow_dispatch` and file attachment
when a GitHub release is published. Server package names include the resolved
release version, for example
`rch-rust-full-linux-amd64-v3.0.0-preview.26.tar.gz`; the same version, Git ref,
and commit SHA are written into `release-manifest.json` inside the archive.
Manual workflow runs label artifacts with the `release_version` input, or with
the branch name when that input is blank.

For a Linux AMD64 server testing candidate, set `linux_amd64_only=true` on a
manual run or include `<!-- rch-release: linux-amd64-only -->` in the published
release body. This builds the full Linux AMD64 archive and its checksum, with
the pinned daemon, UI, and TAK service; desktop and other platform jobs are
skipped. Published releases own asset builds; pushing a tag alone no longer
starts a duplicate package build. Normal releases retain the full matrix.

The release workflow owns all five server packages and both desktop packages.
The next testing candidate is
[`v3.0.0-preview.26`](../docs/release-notes-v3.0.0-preview.26.md), scoped to the
complete Linux AMD64 server archive for DigitalOcean evaluation. Its release
body must include the Linux-only marker above. This candidate does not publish
desktop or other-platform packages. Preview.25 remains the earlier full-matrix
package record; earlier notes are kept under [`docs/`](../docs/).

Local desktop builds normally compile `reticulumd` from the sibling
`LXMF-rs` checkout. Set `RCH_RETICULUMD_BINARY` to an absolute, validated
LXMF 0.15.0 `reticulumd` path when that checkout is intentionally dirty; hosted
packages always build the pinned clean LXMF commit
`392fc1b928af2c30ef4290f78f173d37aa9ef15e`
(`reticulumd-test-0.15.0-rch663-678.1`, SDK `0.15.0`). This source includes
the #678 announce-cache cleanup and #663 resource/ZeroMQ follow-through.
The Rust library dependencies resolve the matching immutable revision without
requiring a sibling checkout. A local daemon build still uses the documented
sibling layout.

The bundled daemon build applies the same Tokio 1.53.3 security update as RCH;
`release-manifest.json` records `lxmf.daemon_tokio_version` alongside the exact
LXMF source commit and daemon checksum.

The upstream standalone Linux AMD64 daemon archive uses static musl. RCH's
existing release workflow rebuilds the pinned source for the host target;
its daemon is not the same published binary. Verify the RCH archive checksum,
its embedded RCH/LXMF source identities and daemon checksum, and the extracted
binaries' actual runtime requirements. Preview.25 Linux binaries required glibc
2.39; do not assume either that floor or upstream's static-musl compatibility
for a new candidate before inspecting its artifacts.

Pull request quality control is handled by
`.github/workflows/rust-pr-quality.yml`. It runs Rust 1.88 formatting, clippy,
locked workspace tests, release builds for the server and TAK service, and
`cargo audit`; the workspace minimum Rust version is 1.88 for the paired LXMF
0.15.0 dependency.

## Python Store Migration

Rust v3 packages use an offline, local-only production migration wrapper before
the Rust server starts. Run a dry run first to inventory the Python store,
Reticulum identity/config inputs, runtime file directories, and target paths:

```powershell
scripts\import-python-rch-production.ps1 -SourceRoot . -LegacyStore RTH_Store -TargetDir target\production-rch-3 -DryRun
```

The dry run writes `migration-plan.json` without copying data or running the
Rust database converter. The apply run copies `config.ini`, `identity`,
Reticulum transport identity/config, `telemetry.db`, root `telemetry.db`, files,
images, and LXMF runtime data, then converts `rth_api.sqlite` into the Rust
`rch_state.sqlite3` snapshot database:

```powershell
scripts\import-python-rch-production.ps1 -SourceRoot . -LegacyStore RTH_Store -TargetDir target\production-rch-3
```

If `rch_state.sqlite3` already exists, the script stops unless `-Force` is
provided. `-Force` backs up the existing database to
`rch_state.sqlite3.before-v3-migration.<timestamp>` before replacing it. The
apply run writes `rust-migration-report.json`, `migration-plan.json`,
`migration-manifest.json`, and a compatibility `MANIFEST.txt` in the target
directory.

`scripts\migrate-python-rch.ps1` remains available as a lightweight local
developer wrapper. The Rust converter is available directly as:

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
  `main`, with server package artifacts and optional desktop artifacts.
- Rust stable: `v3.0.0` after all Rust server and desktop gates pass.
