# Reticulum Community Hub (RCH)

**Community-owned coordination over Reticulum.**

Reticulum Community Hub gives a group a shared place to communicate, maintain a common operational picture, coordinate work, and exchange files over Reticulum and LXMF. It is designed for intermittent links, limited bandwidth, and networks that must remain useful without depending on a central Internet service.

RCH is the hub and operator interface in the R3AKT product family:

> **R3AKT**  
> **Reticulum Resilient Response Tactical Kit**  
> **Democratizing Situational Awareness**

## What RCH provides

RCH adds shared services and persistent state to a Reticulum network:

- targeted, broadcast, and topic-based messaging over LXMF;
- telemetry collection and a shared map with operator-managed markers;
- missions, teams, members, assets, skills, and assignments;
- collaborative checklists for procedures and field tasks;
- Emergency Action Messages and team status summaries;
- file and image storage with topic associations;
- a REST and WebSocket API for clients and integrations;
- an optional TAK connector for Cursor-on-Target chat and position exchange.

SQLite is the durable message-history and delivery-recovery owner. The runtime message
cache keeps at most 500 records and an estimated 32 MiB, with a 30-minute inactivity
limit. `/Chat/Messages` reads durable history, so cache eviction does not remove old
messages or abandon pending delivery. See [bounded persistence](docs/goals/bounded-persistence/EVIDENCE.md)
for the transaction, migration, and validation details.

RCH does not replace Reticulum. Reticulum provides the network. RCH provides the shared coordination services that a community or field team needs on top of it.

## Where it fits

```text
REM, R3AKT Client, and other LXMF applications
                     |
              Reticulum + LXMF
                     |
            LXMF-rs reticulumd
                     |
              RCH Rust server
               /           \
       Web/Desktop UI     REST/WebSocket API
                              |
                     Optional TAK service
                              |
                         TAK network
```

A hub can serve a local group, operate across several Reticulum interfaces, or participate in a larger federation without surrendering local control.

## Project status

RCH is being rewritten in Rust for the 3.0 product line. The current workspace contains the Rust server, shared domain crates, the Reticulum/LXMF transport adapter, the web and desktop application, and a separate TAK connector service.

The Rust edition is currently preview software. Use it for testing, integration work, and community evaluation. Review the release notes before using it for unattended or safety-critical deployments.

The current testing candidate is
[v3.0.0-preview.26](docs/release-notes-v3.0.0-preview.26.md), a Linux AMD64
server prerelease for DigitalOcean evaluation. It pairs LXMF-rs SDK 0.15.0
with [`reticulumd-test-0.15.0-rch663-678.1`](https://github.com/FreeTAKTeam/LXMF-rs/releases/tag/reticulumd-test-0.15.0-rch663-678.1)
at immutable revision `392fc1b928af2c30ef4290f78f173d37aa9ef15e`.
The existing release workflow builds the complete Linux AMD64 server archive
and a Debian installer using Debian 12 (Bookworm) and Rust 1.88;
other server platforms and desktop packages are outside this candidate's scope.
[Preview.25](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/releases/tag/v3.0.0-preview.25)
remains the earlier full-platform package record. Release notes for every
preview are attached to its
[GitHub release](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/releases);
older notes are kept under [`docs/`](docs/).
Install the server and daemon from the same package or pinned revision. The
AMD64 Debian package targets Debian 12 or later and compatible Ubuntu releases
whose libraries satisfy its declared dependencies. It includes the UI and
paired daemon, and requires no Rust, Node.js or Python toolchain to install.

The server package workflow selects Tokio 1.53.3 before its locked daemon
build. `release-manifest.json` records the configured requirement as
`lxmf.required_daemon_tokio_version`, alongside the LXMF source commit and
daemon checksum. The workflow build log verifies dependency selection;
package assembly does not infer a Tokio version from an arbitrary binary.

The Python 2.9.x edition is preserved on the [`rch-python`](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/tree/rch-python) branch for critical maintenance and reference behavior.

The implementation, migration, and validation notes that previously occupied this README are now referenced from [the Rust migration status document](docs/rust-migration-status.md).

## Getting started

### Install a packaged build

The simplest route is to use a package from
[GitHub Releases](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/releases).
On a supported Debian or Ubuntu AMD64 host, download the `.deb` and its
`.sha256` file, verify the checksum, then install it with
`sudo apt install ./rch-server_3.0.0~preview.26-1_amd64.deb`. Configure
`/etc/rch` before explicitly enabling services; installation does not start
them. See [the packaging instructions](packaging/README.md#debian-amd64-installation)
for configuration, upgrade preservation and startup. Server archives and
desktop packages have their own release notes and platform requirements.

### Build the Rust server from source

Requirements:

- Rust 1.88 or newer for the server workspace and Tauri desktop shell;
- a local Reticulum configuration;
- [`LXMF-rs`](https://github.com/FreeTAKTeam/LXMF-rs) `reticulumd` for live LXMF transport;
- Node.js and npm only when building the web or desktop interface.

Clone and build the server:

```bash
git clone https://github.com/FreeTAKTeam/Reticulum-Community-Hub.git
cd Reticulum-Community-Hub
cargo build --release -p r3akt-rch-server
```

Start the HTTP server for local development:

```bash
cargo run -p r3akt-rch-server -- \
  --bind 127.0.0.1:8080 \
  --db-path ./rch-runtime.db \
  --config-path ./config.ini \
  --reticulum-config-path "$HOME/.reticulum/config" \
  --api-key change-this-preview-key
```

This starts the RCH API and local state service. A live mesh deployment also requires the LXMF-rs ZeroMQ endpoints and a local Reticulum destination. See [Rust migration status](docs/rust-migration-status.md) for the current runtime path and development commands.

Replace the example key with a unique credential. Protected routes, including
`/Status`, `/diagnostics/runtime`, internal adapters and WebSocket streams,
require authentication even on loopback. To enroll through the local first-run
UI instead, omit `--api-key` and add `--ui-dist-path ./ui/dist` after building
the shared UI. Documentation and local setup remain available before enrollment.

RCH requires the paired daemon durable broker (`--zmq-durable-broker`). Its
persisted inbox and outbound intents replace legacy event polling and retry
ownership. See [durable broker cutover](docs/durable-broker.md) before upgrading
an existing deployment.

For an already running daemon, use its command endpoint and a response endpoint
owned by this RCH instance:

```bash
cargo run -p r3akt-rch-server -- \
  --bind 127.0.0.1:8080 --db-path ./rch-runtime.db \
  --config-path ./config.ini --api-key change-this-preview-key \
  --lxmf-zmq-command tcp://127.0.0.1:9100 \
  --lxmf-zmq-response tcp://127.0.0.1:9101 \
  --ui-dist-path ./ui/dist
```

RCH registers and derives its service destination. `--reticulumd-source` is
optional and only asserts that registered RCH destination.

To let RCH manage the matching daemon, add
`--reticulumd-exe ../LXMF-rs/target/release/reticulumd`, and provide
`--reticulumd-db-path ./reticulum.db` and
`--reticulum-config-path "$HOME/.reticulum/config"`. Build that daemon with
`zmq-pipeline-rpc` enabled. Verify `/Status` and `/diagnostics/runtime`; a
daemon-backed launch must show the configured source and running daemon.

Remote browser connections require HTTPS/WSS. For a TLS proxy or separately
hosted UI, set exact comma-separated `RCH_ALLOWED_ORIGINS` values such as
`https://rch.example.org`. Local loopback HTTP/WS remains supported.

After startup, useful local endpoints include:

- `http://127.0.0.1:8080/Status`
- `http://127.0.0.1:8080/Help`
- `http://127.0.0.1:8080/openapi.json`
- `http://127.0.0.1:8080/diagnostics/runtime`

## Examples

The maintained [examples guide](docs/examples.md) walks through server startup,
authentication, health and runtime diagnostics, topics, direct/topic/broadcast
chat, files, missions and checklists, WebSockets, Reticulum ZeroMQ attachment,
and the standalone TAK sidecar. The live server also exposes a compact
plaintext quick reference at `GET /Examples`.

For a first authenticated request:

```bash
curl -H 'X-API-Key: change-this-preview-key' \
  http://127.0.0.1:8080/Status
```

For operational deployment and failure diagnosis, continue with the
[operations and troubleshooting guide](docs/operations-and-troubleshooting.md).
For large user inventories, see [identity directory pagination](docs/identity-directory-pagination.md).

## Main components

| Component | Purpose |
| --- | --- |
| `r3akt-rch-server` | HTTP, WebSocket, persistence, UI hosting, and RCH runtime |
| `r3akt-rch-core` | Missions, teams, checklists, topics, delivery state, and authorization |
| `r3akt-transport-rns` | Reticulum and LXMF integration through LXMF-rs |
| `r3akt-profile-rch` | RCH command, result, and event fields on LXMF |
| `r3akt-protocol` | Shared MessagePack envelopes and acknowledgement types |
| `r3akt-identity` | Identity, trust, and enrollment decisions |
| `r3akt-tak-connector` | Independent TAK and Cursor-on-Target bridge service |
| `ui/` | Shared Vue operator interface |
| `apps/rch-desktop/` | Tauri desktop packaging |

## Related projects

- [REM: Reticulum Mobile Emergency Management](https://github.com/FreeTAKTeam/reticulum_mobile_emergency_management)
- [R3AKT Client](https://github.com/FreeTAKTeam/R3AKTClient)
- [LXMF-rs](https://github.com/FreeTAKTeam/LXMF-rs)
- [FreeTAKTeam repositories](https://github.com/FreeTAKTeam)

## Development and verification

Before submitting a pull request, run the Rust quality checks:

```bash
cargo fmt --all -- --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
```

The repository also contains release-readiness scripts and live Reticulum validation tools. These are documented in [Rust migration status](docs/rust-migration-status.md).

## Contributing

Issues, tests, documentation corrections, and pull requests are welcome. Keep changes focused, explain the user-visible effect, and add tests for modified runtime behavior.

For substantial protocol or architecture changes, open an issue first so the wire contract and compatibility impact can be discussed before implementation.

## License

RCH is licensed under the [Eclipse Public License 2.0](LICENSE).
