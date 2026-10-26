# RCH v3.0.0-preview.26 — Linux AMD64 integration testing

<!-- rch-release: linux-amd64-only -->

Preview.26 is a testing-only Linux AMD64 server candidate for DigitalOcean
evaluation. It combines the RCH audit corrections with LXMF-rs SDK 0.15.0
and the daemon source from
[`reticulumd-test-0.15.0-rch663-678.1`](https://github.com/FreeTAKTeam/LXMF-rs/releases/tag/reticulumd-test-0.15.0-rch663-678.1),
immutable commit `392fc1b928af2c30ef4290f78f173d37aa9ef15e`.
This source includes the #678 announce-cache cleanup and #663 resource/ZeroMQ
follow-through. This release does not claim that production resource growth
or delayed delivery is resolved.

## Scope and changes

The existing release workflow builds
`rch-rust-full-linux-amd64-v3.0.0-preview.26.tar.gz` and
`rch-server_3.0.0~preview.26-1_amd64.deb`, each with a `.sha256` file. Both
contain `r3akt-rch-server`, `r3akt-tak-service`, the matching ZeroMQ-capable
`reticulumd`, the shared UI, service helpers, configuration templates,
documentation and `release-manifest.json`. The Debian package adds managed
configuration, a system account and systemd units. Other server platforms and
desktop bundles are outside this candidate's scope.

RCH corrections preserve subscription IDs and multiple topic subscriptions
across restart; select current map telemetry per peer; preserve multi-event
emergency log content; prevent oversized fanout from blocking the ordered
inbox; and remove the unsafe stale saved-PID stop fallback. The TAK bridge
keeps one managed marker per source UID, preserves operator names, updates
position and classification together, and ignores older source observations.
First-run setup selects the configured daemon format; TOML validation rejects
incompatible INI before setup, apply or rollback changes files. Python setup
retains its INI serialization. Historical duplicate TAK markers are retained. The desktop launch correction
is in source; this Linux server candidate does not publish a new desktop build.

Both Rust lockfiles select Tokio 1.53.3 for RUSTSEC-2026-0386. The paired
upstream daemon lockfile has Tokio 1.53.2, so the package workflow also applies
Tokio 1.53.3 before its locked daemon build. The configured requirement is
recorded as `lxmf.required_daemon_tokio_version` in the release manifest;
the server workflow build log verifies dependency selection, while package
assembly does not inspect a supplied binary's embedded Tokio version. The
LXMF source commit remains unchanged. The workspace dependency audit continues
to deny warnings without an advisory exception. No desktop dependency
qualification is claimed by this Linux server candidate.

## Linux runtime requirements

Use a 64-bit x86_64/AMD64 host running Debian 12 or later, or a compatible
Ubuntu release whose libraries satisfy the package's declared dependencies.
The Linux AMD64 server workflow builds all three binaries in Debian 12
(Bookworm) with Rust 1.88. `dpkg-shlibdeps` derives the installer's runtime
library dependencies from those binaries; apt resolves them during install.
Installing the package requires no Rust, Node.js or Python toolchain.

The upstream standalone daemon archive is static musl; RCH rebuilds the same
source and packages a different binary. Verify the actual published runtime
dependencies before recording compatibility. For archive installation, inspect
the extracted binaries with `file` and `ldd` and confirm that the host supplies
their required libraries and glibc versions.

## Download and preserve an existing deployment

Before upgrading an existing deployment, stop RCH and its daemon and back up
the complete state, SQLite databases, identities, attachment directories and
configuration consistently. Do not copy a live main SQLite database file
alone. Preserve credentials, service accounts, paths, ownership, interface
settings and service overrides. Keep the previous binaries/package. Do not
erase retained history to obtain a lower memory result. Rollback requires the
pre-upgrade backups and reconciliation of work admitted afterward; do not run
old binaries against a migrated database.

For Debian installation, download the package and checksum from the prerelease
into the same directory:

```bash
set -e
asset='rch-server_3.0.0~preview.26-1_amd64.deb'
release='https://github.com/FreeTAKTeam/Reticulum-Community-Hub/releases/download/v3.0.0-preview.26'
curl -fLO "$release/$asset"
curl -fLO "$release/$asset.sha256"
sha256sum -c "$asset.sha256"
sudo apt install "./$asset"
```

The package installs under `/opt/rch`, creates the `rch` system account and
uses `/var/lib/rch` for state and `/var/log/rch` for logs. It does not enable
or start services. Configure a unique `RTH_API_KEY` in
`/etc/rch/rch-server.env`, review `/etc/rch/config.ini`, and configure the
actual Reticulum interfaces in `/etc/rch/reticulumd.toml`. Defaults have no
interfaces and disable discovery. Review dpkg upgrade prompts to retain or
merge existing configuration. Package removal retains configuration, state,
logs and the account; purge removes dpkg-managed configuration files while
retaining state, logs and the account.

To use the full archive instead, download it and its checksum, verify, and
extract into a new directory:

```bash
set -e
asset='rch-rust-full-linux-amd64-v3.0.0-preview.26.tar.gz'
release='https://github.com/FreeTAKTeam/Reticulum-Community-Hub/releases/download/v3.0.0-preview.26'
curl -fLO "$release/$asset"
curl -fLO "$release/$asset.sha256"
sha256sum -c "$asset.sha256"
install="$HOME/rch-preview.26"
mkdir "$install"
tar -xzf "$asset" -C "$install"
cd "$install"
```

## Start and verify on the test host

After configuring the Debian installation, start it explicitly:

```bash
sudoedit /etc/rch/rch-server.env
sudo -u rch -- vi /etc/rch/config.ini /etc/rch/reticulumd.toml
sudo systemctl enable --now rch-server
```

The mutable configuration files belong to `rch`; edit them as that account
(or use the authenticated setup flow). The root-owned environment file stays
protected. First-run setup emits daemon TOML for this package; the legacy INI
Reticulum editor is not a TOML editor. After changing daemon configuration,
restart both services with `sudo systemctl restart reticulumd rch-server`.

`rch-server.service` requires and starts `reticulumd.service`. Vendor units
are in `/usr/lib/systemd/system`; use systemd overrides for operator changes.
Hub and transport identities default to `/var/lib/rch/identity` and
`/var/lib/rch/reticulum-identity`. Daemon RPC uses the private Unix socket
`/run/rch/reticulumd.sock`. Inspect `journalctl -u rch-server -u reticulumd`
when checking startup. Upgrades stop both services and require an explicit
restart after configuration review.

For archive installation, the following Bash example uses a managed daemon.
Set these paths to the existing deployment's actual locations. Do not run
this alongside the Debian services or another owner of the same daemon:

```bash
RCH_STATE=/absolute/path/to/existing/rch-state
RCH_CONFIG=/absolute/path/to/existing/config.ini
RETICULUM_CONFIG=/absolute/path/to/existing/reticulumd.toml
./bin/r3akt-rch-server \
  --bind 127.0.0.1:8000 \
  --db-path "$RCH_STATE/rch_state.sqlite3" \
  --config-path "$RCH_CONFIG" \
  --reticulumd-exe "$PWD/bin/reticulumd" \
  --reticulumd-db-path "$RCH_STATE/reticulum.db" \
  --reticulum-config-path "$RETICULUM_CONFIG" \
  --lxmf-zmq-command tcp://127.0.0.1:9100 \
  --lxmf-zmq-response tcp://127.0.0.1:9101 \
  --ui-dist-path "$PWD/ui"
```

Retain the existing password/API-key configuration. For a separate daemon,
keep the existing service arrangement, use the paired binary with
`--zmq-durable-broker`, and keep its endpoints aligned with RCH. Do not pass a
placeholder `--reticulumd-source`; let RCH register its service identity.
Broker-only startup does not create Reticulum interfaces or listeners. A real
mesh test needs the existing configured interfaces as well as HTTP readiness.

Keep ports 8000, 9100 and 9101 owned by this one test instance, or preserve the
existing alternative port assignments. For a remote DigitalOcean host, use
`ssh -L 8000:127.0.0.1:8000 user@your-host` and open the loopback UI. Persistent
remote browser access requires HTTPS/WSS and exact `RCH_ALLOWED_ORIGINS`, as
explained in [the operations guide](operations-and-troubleshooting.md).

Check authenticated `/Status` and `/diagnostics/runtime` together. Verify the
matching ZeroMQ backend, registered service identity, running paired daemon,
healthy durable-broker lanes, progress and error counters. For transport
acceptance, trace a unique fresh message through custody and application to an
actual recipient receipt. A command being accepted or HTTP 200 alone does not
prove delivery.

## Validation record and remaining acceptance

On 2026-10-26 the local `-ServerOnlyAlpha` gate passed with 716 workspace
tests and two existing specialized ignores, strict Clippy and Rustdoc, local
link validation, the optimized server build and authenticated HTTP smoke.
The strict workspace dependency audit passed for 291 locked dependencies,
and the standalone TAK service release build passed. PR #281 passed all
13 hosted checks before merging. Public package and deployment qualification
remain separate from these source checks.

Record the final RCH source SHA, paired source SHA, CI runs and local checks
against the actual release commit. The committed gate is
`scripts/release-readiness.ps1 -ServerOnlyAlpha`; dependency audit, affected UI
checks and any configured live gates are separate evidence. Its default HTTP
smoke runs without a daemon, so package qualification also needs a managed
bundled-daemon smoke with temporary state and owned endpoints. Independently
verify both public package checksums, all embedded manifest identities and
the packaged daemon checksum before recording package acceptance. Verify
Debian installation, upgrade/removal preservation and paired-daemon startup
from the actual package; the local source gate does not establish those results.

These instructions do not assert future CI, artifact verification or an actual
DigitalOcean deployment has passed. Multi-hour production memory/swap behavior,
the reported two-core workload, restart/recovery under sustained traffic,
physical power loss, hardware/public-network client receipt and native desktop
GUI operation remain unverified by this candidate description. The upstream
release also retains measured resource limits and large-transaction risks;
see its [acceptance record](https://github.com/FreeTAKTeam/LXMF-rs/blob/392fc1b928af2c30ef4290f78f173d37aa9ef15e/docs/performance/rch-resource-fixes-663.md).
GitHub testing packages do not imply a crates.io or container-image release.
