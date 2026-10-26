# RCH v3.0.0-preview.29 — paired LXMF-rs testing build

<!-- rch-release: linux-amd64-only -->

Preview.29 is a Linux AMD64 testing pair for DigitalOcean evaluation. It uses
LXMF-rs SDK and daemon 0.15.0 from immutable source
`6782e899ff3feebf221397517dca8525a5c70661`, published as
[`reticulumd-test-0.15.0-rch663-678.3`](https://github.com/FreeTAKTeam/LXMF-rs/releases/tag/reticulumd-test-0.15.0-rch663-678.3).
SDK contract 2/v2.6 and the durable ZeroMQ transport remain the pairing contract.
RCH and its rebuilt bundled daemon select Tokio 1.53.3; the source rebuild
security override is recorded below.

## Changes from preview.28

This candidate uses the explicitly requested LXMF-rs `.3` source at
`6782e899ff3feebf221397517dca8525a5c70661` for SDK dependencies, CI and bundled
daemon. The SDK/daemon remain 0.15.0 with contract 2/v2.6. The source code is
identical to preview.28's paired source; their only upstream difference is
Tokio's lockfile entry.

RCH retains its Tokio 1.53.3 security requirement. The release workflow builds
`reticulumd` from `.3`/`6782e899` and explicitly updates its Tokio 1.53.2 lock
entry to 1.53.3 before the locked build. This is a source rebuild with the
recorded security patch, not a repackaging of the standalone `.3` executable.
The root RCH lockfile also remains on Tokio 1.53.3.

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

- `rch-server_3.0.0.preview.29-1_amd64.deb` and its `.sha256` file;
- `rch-rust-full-linux-amd64-v3.0.0-preview.29.tar.gz` and its `.sha256` file.

Both include the server, matched `reticulumd`, standalone TAK service, shared
UI and `release-manifest.json`. The AMD64 binaries are built on Debian 12
(Bookworm) with Rust 1.88; apt resolves the installer's declared dependencies.
No Rust, Node.js or Python toolchain is needed on the test host. Desktop and
other-platform bundles are outside this server candidate's scope.

```bash
set -e
asset='rch-server_3.0.0.preview.29-1_amd64.deb'
release='https://github.com/FreeTAKTeam/Reticulum-Community-Hub/releases/download/v3.0.0-preview.29'
curl -fLO "$release/$asset"
curl -fLO "$release/$asset.sha256"
sha256sum -c "$asset.sha256"
sudo apt install "./$asset"
```

The installed Debian version is `3.0.0~preview.29-1`; the asset filename uses
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
