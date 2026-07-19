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

The Python 2.9.x edition is preserved on the [`rch-python`](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/tree/rch-python) branch for critical maintenance and reference behavior.

The implementation, migration, and validation notes that previously occupied this README are now referenced from [the Rust migration status document](docs/rust-migration-status.md).

## Getting started

### Install a packaged build

The simplest route is to use a package from [GitHub Releases](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/releases). Release assets may include server archives and desktop packages. Check the notes for the supported operating systems and the exact components included in each preview.

### Build the Rust server from source

Requirements:

- Rust 1.85 or newer for the server workspace, and Rust 1.88 or newer for the
  Tauri desktop shell;
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
  --reticulum-config-path "$HOME/.reticulum/config"
```

This starts the RCH API and local state service. A live mesh deployment also requires the LXMF-rs ZeroMQ endpoints and a local Reticulum destination. See [Rust migration status](docs/rust-migration-status.md) for the current runtime path and development commands.

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
