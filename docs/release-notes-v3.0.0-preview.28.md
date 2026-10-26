# RCH v3.0.0-preview.28 — paired LXMF-rs testing build

<!-- rch-release: linux-amd64-only -->

Preview.28 is a Linux AMD64 testing pair for DigitalOcean evaluation. It uses
LXMF-rs SDK and daemon 0.15.0 from immutable source
`a690ab0b501e03719364aac3d6a18bb715ccd531`, published as
[`reticulumd-test-0.15.0-rch663-678.4`](https://github.com/FreeTAKTeam/LXMF-rs/releases/tag/reticulumd-test-0.15.0-rch663-678.4).
SDK contract 2/v2.6 and the durable ZeroMQ transport remain the pairing contract.
Both RCH and the paired LXMF source lockfile select Tokio 1.53.3.

## Changes from preview.27

Preview.28 corrects the paired standalone release tag from `.3` to `.4`.
Another publisher reserved `.3` at source `6782e899ff3feebf221397517dca8525a5c70661`
while preview.27 was building. Preview.27 already contained the correct tested
`a690ab0b501e03719364aac3d6a18bb715ccd531` SDK and daemon; only its standalone
release alias was wrong. This release keeps those sources and the Tokio 1.53.3
security fix, and corrects the immutable package metadata. Existing `.3` and
preview.27 artifacts are preserved.

## Included LXMF corrections since preview.26

The updated paired source contains the merged LXMF regression corrections:

- Dirty persistence runs on a bounded timer and seeds restored cache fingerprints.
- Readiness waits for configured ZeroMQ binds; broker control waits are bounded.
- Replay-safe SDK calls recover from broker writer deadlines while retaining
  queued commit and request-identity semantics.
- WAL maintenance uses a dedicated connection outside the traffic writer mutex.
- Delivery-owner receipts retain native packet bindings.

RCH's SDK dependencies, CI pins, runtime baseline and bundled daemon all use
the same immutable revision. Existing RCH audit and first-run TOML corrections
are retained. This candidate adds no UI redesign or deployment automation.
The source API version remains 0.15.0; hashes identify the new testing build.

## Packages and installation

The existing release workflow produces:

- `rch-server_3.0.0.preview.28-1_amd64.deb` and its `.sha256` file;
- `rch-rust-full-linux-amd64-v3.0.0-preview.28.tar.gz` and its `.sha256` file.

Both include the server, matched `reticulumd`, standalone TAK service, shared
UI and `release-manifest.json`. The AMD64 binaries are built on Debian 12
(Bookworm) with Rust 1.88; apt resolves the installer's declared dependencies.
No Rust, Node.js or Python toolchain is needed on the test host. Desktop and
other-platform bundles are outside this server candidate's scope.

```bash
set -e
asset='rch-server_3.0.0.preview.28-1_amd64.deb'
release='https://github.com/FreeTAKTeam/Reticulum-Community-Hub/releases/download/v3.0.0-preview.28'
curl -fLO "$release/$asset"
curl -fLO "$release/$asset.sha256"
sha256sum -c "$asset.sha256"
sudo apt install "./$asset"
```

The installed Debian version is `3.0.0~preview.28-1`; the asset filename uses
periods so GitHub's filename normalization cannot invalidate the checksum.

Before upgrading, stop both services and back up the complete configuration,
databases, identities, attachments and other state consistently. Retain the
existing credentials, interfaces, paths, ownership and systemd overrides.
Review dpkg configuration prompts and preserve or merge operator settings.
The installer preserves state and does not enable or start services.

Configure `/etc/rch` using [the Debian package guide](../packaging/README.md#debian-amd64-installation),
then explicitly start `rch-server` and its required daemon. Defaults use
loopback HTTP/ZeroMQ and no Reticulum interfaces. First-run setup writes TOML
for this daemon; use the documented TOML configuration rather than the legacy
INI editor. Restart both services after changing daemon configuration.
For remote UI testing, an SSH tunnel to `127.0.0.1:8000` keeps the default bind.

## Qualification and testing boundary

Run the committed `scripts/release-readiness.ps1 -ServerOnlyAlpha`, strict
workspace audit, and affected checks. Its default HTTP smoke does not exercise
a daemon. Package qualification also requires checksum and manifest validation,
Debian install/upgrade/remove preservation, and an installed paired-daemon
smoke covering UI/authentication, enrollment, broker readiness and restart.
Final source, CI links, binary hashes and public-download results are recorded
on the published release after those checks run.

Use `/Status` together with `/diagnostics/runtime` to inspect the actual
ZeroMQ backend, registered service identity, broker lanes, poll progress and
errors. Trace a fresh test message through a recipient receipt before claiming
delivery. HTTP readiness or custody acceptance alone does not prove it.

This is a testing release. The previous regression work's sustained resource
acceptance remains open; no production memory/swap plateau or delayed-delivery
resolution is claimed. DigitalOcean deployment, delivery to real peers,
long-running load, physical power loss and desktop GUI operation remain
separate acceptance. No crates.io or container-image publication is implied.
