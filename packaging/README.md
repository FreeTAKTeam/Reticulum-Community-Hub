# RCH Rust Packaging

The Rust packaging line now has two release package shapes:

- Server package: deployable `r3akt-rch-server` binary, `r3akt-tak-service`
  binary, checksum-recorded LXMF `0.16.0` `reticulumd` binary with ZeroMQ
  support, mandatory ZeroMQ southbound configuration, shared UI bundle, service
  helper files, config templates, and checksums. Current release CI builds
  Windows x64, macOS x64, macOS arm64, Linux AMD64, and Linux Raspberry Pi 64
  server archives. Linux AMD64 also produces a Debian `.deb` installer and
  checksum from the same full server payload.
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
`rch-rust-full-linux-amd64-v3.0.0-preview.33.tar.gz`; the same version, Git ref,
and commit SHA are written into `release-manifest.json` inside the archive.
Manual workflow runs label artifacts with the `release_version` input, or with
the branch name when that input is blank.

For a Linux AMD64 server testing candidate, set `linux_amd64_only=true` on a
manual run or include `<!-- rch-release: linux-amd64-only -->` in the published
release body. This builds the full Linux AMD64 archive, Debian installer and
their checksums, with the pinned daemon, UI, and TAK service; desktop and other
platform jobs are skipped. Published releases own asset builds; pushing a tag
alone no longer starts a duplicate package build. Normal releases retain the
full matrix. Versioned releases such as `v3.0.0-preview.33` produce
`rch-server_3.0.0.preview.33-1_amd64.deb`; a manual branch label without a
release version produces only the archive.

The release workflow owns all five server packages and both desktop packages.
The current testing candidate is
[`v3.0.0-preview.33`](../docs/release-notes-v3.0.0-preview.33.md), scoped to the
complete Linux AMD64 server archive and Debian installer for DigitalOcean
evaluation. Its release body must include the Linux-only marker above. This candidate does not publish
desktop or other-platform packages. Preview.25 remains the earlier full-matrix
package record; earlier notes are kept under [`docs/`](../docs/).

Local desktop builds normally compile `reticulumd` from the sibling
`LXMF-rs` checkout. Set `RCH_RETICULUMD_BINARY` to an absolute, validated
LXMF 0.16.0 `reticulumd` path when that checkout is intentionally dirty; hosted
packages use the pinned clean LXMF commit
`c45a5113807fdf5618b55d4e6ba7f598c3eaafe7`
(`reticulumd-test-0.16.0-linux-c45a5113.1`, SDK `0.16.0`). This source also includes the merged timer-driven persistence, broker deadline
recovery, dedicated WAL maintenance, and native packet receipt-binding fixes.
The Rust library dependencies resolve the matching immutable revision without
requiring a sibling checkout. A local daemon build still uses the documented
sibling layout.

The server package workflow selects Tokio 1.53.3 before its locked daemon
build. `release-manifest.json` records the configured requirement as
`lxmf.required_daemon_tokio_version`, alongside the exact LXMF source commit
and daemon checksum. The workflow build log verifies dependency selection;
assembly of a supplied binary does not inspect its embedded Tokio version.
This candidate does not qualify a desktop sidecar build.

The Linux AMD64 server workflow builds the RCH and TAK binaries in a Debian 12
(Bookworm) container with Rust 1.88 and packages the checksum-verified upstream
static musl daemon. `scripts/build-debian-package.sh` derives
runtime library dependencies from those binaries using `dpkg-shlibdeps`.
The installer targets Debian 12 or later and compatible Ubuntu AMD64 hosts
that satisfy its declared dependencies. Other architectures and desktop
packages retain their separate build environments.

The Linux AMD64 package includes the exact daemon from the upstream standalone
archive, verified against its pinned SHA-256 before assembly. Verify checksums, embedded RCH/LXMF
source identities, the daemon checksum and actual runtime dependencies before
recording package acceptance. Earlier Linux package requirements do not
establish the new candidate's compatibility.

Pull request quality control is handled by
`.github/workflows/rust-pr-quality.yml`. It runs Rust 1.99.1 formatting, clippy,
locked workspace tests, release builds for the server and TAK service, and
`cargo audit`; the workspace minimum Rust version is 1.88 for the paired LXMF
0.16.0 dependency.

## Debian AMD64 installation

Download `rch-server_3.0.0.preview.33-1_amd64.deb` and its `.sha256` file from
the same release into one directory. Verify before installing:

```bash
sha256sum -c rch-server_3.0.0.preview.33-1_amd64.deb.sha256
sudo apt install ./rch-server_3.0.0.preview.33-1_amd64.deb
```

The package installs binaries, UI and the release manifest under `/opt/rch`.
It creates the `rch` system account and state/log directories `/var/lib/rch`
and `/var/log/rch`. Package-managed configuration files are
`/etc/rch/config.ini`, `/etc/rch/rch-server.env` and `/etc/rch/reticulumd.toml`.
Vendor service units live under `/usr/lib/systemd/system`; use systemd
overrides for operator changes.

Installation does not enable or start services. Set a unique `RTH_API_KEY` in
`rch-server.env`, review the hub identity and state paths in `config.ini`, and
configure the actual Reticulum interfaces in `reticulumd.toml`. Its defaults
have no interfaces and disable discovery. Then start explicitly:

```bash
sudoedit /etc/rch/rch-server.env
sudo -u rch -- vi /etc/rch/config.ini /etc/rch/reticulumd.toml
sudo systemctl enable --now rch-server
```

The mutable configuration files belong to `rch` for authenticated setup and
atomic updates. The sticky configuration directory protects the root-owned
environment file from replacement by the service account. Edit mutable files
as `rch`. First-run setup emits the daemon's TOML format; the legacy INI
Reticulum editor does not edit TOML. After configuration changes, run
`sudo systemctl restart reticulumd rch-server`.

`rch-server.service` requires and starts `reticulumd.service`. The UI/API bind
to `127.0.0.1:8000`, ZeroMQ uses loopback ports 9100/9101, and daemon RPC uses
the private `/run/rch/reticulumd.sock`. Hub and transport identities live at
`/var/lib/rch/identity` and `/var/lib/rch/reticulum-identity`. Check authenticated
`/Status` and `/diagnostics/runtime`, both service journals, and an actual
recipient receipt before claiming transport readiness. The packaged TAK
service is available but is not started automatically.

Before upgrading an existing deployment, stop both services and back up its
complete configuration, identities, databases and attachment directories
consistently. Preserve the existing credentials, interfaces, state paths,
service overrides and ownership. Review any dpkg configuration-file prompt;
keep or merge operator settings rather than replacing them blindly. Package
upgrade stops the services and leaves restarting them to the operator.
Removing the package preserves `/etc/rch`, state, logs and the system account.
Purging also removes dpkg-managed configuration files; state, logs and the
account remain. Keep the previous package and pre-upgrade backups for rollback;
an older binary must not be run against a migrated database.

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
