# RCH Rust migration status

This document keeps implementation and release-engineering information out of the project landing page. It is intended for maintainers, contributors, and integration developers.

## Source report

The detailed technical report that previously occupied the root README is preserved in Git history:

- [README before the introductory rewrite](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/blob/8253b4be9d1d48f4066bda7110b4ac3603c080c7/README.md)

That snapshot contains the full crate inventory, parity matrix, route list, validation history, local test commands, live Reticulum gates, and TAK connector notes as they existed at commit `8253b4be9d1d48f4066bda7110b4ac3603c080c7`.

Do not copy dated test results back into the root README. Update focused documents or release notes instead.

## Migration direction

RCH is moving from the Python 2.9.x implementation to a Rust 3.0 implementation.

- The Rust workspace is the replacement path for the server, persistence layer, web API, WebSocket streams, UI hosting, and desktop packages.
- The Python implementation remains available on the `rch-python` branch for critical maintenance and as a behavioral reference.
- The Rust server must match accepted Python API and wire behavior before the corresponding Python path is retired.
- Preview packages remain test releases until the 3.0 release criteria are met.

## Runtime path

The supported southbound data path is:

```text
r3akt-rch-server
        |
  ZmqDataPlane
        |
   LXMF-rs SDK
        |
   reticulumd
        |
 Reticulum interfaces
```

ZeroMQ is the production data plane between RCH and `reticulumd`. RPC is reserved for control operations where an SDK operation is not available. The server persists outbound intent before admission and leaves network scheduling and delivery receipts to `reticulumd` after acceptance.

TAK integration is a separate service boundary:

```text
TAK network <-> r3akt-tak-service <-> RCH northbound API
```

The main RCH server does not own the TAK socket lifecycle.

## Main Rust crates

| Crate | Responsibility |
| --- | --- |
| `r3akt-rch-server` | HTTP, WebSocket, persistence, UI hosting, runtime lifecycle, and outbound workers |
| `r3akt-rch-core` | Topics, subscribers, missions, teams, assets, checklists, authorization, and durable state |
| `r3akt-transport-rns` | LXMF-rs wire mapping, ZeroMQ transport, batching, events, and delivery status |
| `r3akt-profile-rch` | RCH LXMF command, result, and event field compatibility |
| `r3akt-protocol` | Typed MessagePack envelopes and acknowledgement lifecycle |
| `r3akt-identity` | Identity, trust, enrollment, and moderation helpers |
| `r3akt-tak-connector` | Cursor-on-Target encoding, TAK transports, and standalone bridge service |

## Current parity areas

The Rust implementation covers the principal northbound route families and persistent state used by the UI, including:

- topics, subscribers, clients, chat, files, and images;
- telemetry, events, status, diagnostics, and control routes;
- missions, teams, members, assets, skills, assignments, rights, and mission links;
- markers, zones, Emergency Action Messages, and shared checklists;
- WebSocket streams for system events, telemetry, and messages;
- inbound RCH commands and outbound recipient fanout through LXMF-rs;
- a separately deployable TAK connector service.

Remaining release work is mainly external validation, less common parity cases, migration tooling for existing Python databases, and final packaging evidence.

The retired `r3akt-node`, `r3akt-router`, and `r3akt-store` prototypes are no
longer part of the source tree. Supported examples compile as workspace
members against `r3akt-identity`, `r3akt-profile-rch`, and `r3akt-rch-core`.

## Local server

A local HTTP-only development process can be started with:

```bash
cargo run -p r3akt-rch-server -- \
  --bind 127.0.0.1:8080 \
  --db-path ./rch-runtime.db \
  --config-path ./config.ini \
  --reticulum-config-path "$HOME/.reticulum/config"
```

For outbound and inbound LXMF traffic, add the ZeroMQ command and response endpoints plus the local source destination:

```bash
cargo run -p r3akt-rch-server -- \
  --bind 127.0.0.1:8080 \
  --db-path ./rch-runtime.db \
  --config-path ./config.ini \
  --reticulum-config-path "$HOME/.reticulum/config" \
  --lxmf-zmq-command tcp://127.0.0.1:9100 \
  --lxmf-zmq-response tcp://127.0.0.1:9101 \
  --reticulumd-source <local-destination>
```

The exact daemon and packaging commands may change during preview development. Prefer the release notes and committed scripts over copied commands in external documentation.

## Verification

Minimum Rust checks:

```bash
cargo fmt --all -- --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
cargo +1.85.0 check --workspace --all-targets --locked
RUSTDOCFLAGS="-D warnings" cargo doc --workspace --no-deps
cargo audit --deny warnings
cargo build --release -p r3akt-rch-server
npm --prefix ui run typecheck
```

The repository also provides:

- `scripts/release-readiness.ps1` for the server alpha gate;
- `scripts/local-reticulum-live-gate.ps1` for local multi-daemon delivery, fanout, event polling, and load checks;
- `docs/examples.md` for maintained northbound, WebSocket, Reticulum, and TAK examples;
- `docs/operations-and-troubleshooting.md` for deployment diagnostics and failure handling;
- GitHub Actions workflows for formatting, clippy, workspace tests, release builds, audit checks, packaging, and artifact publication.

Live TAK and external Reticulum checks require explicitly configured infrastructure and must not run with copied public endpoints or credentials.

## Documentation policy

Use the root README for stable, first-contact information only.

Place detailed material according to its purpose:

- architecture and service ownership in architecture documents;
- wire contracts and payload examples in protocol documents;
- release evidence in release notes or a dated release-evidence document;
- commands used only by maintainers in this document or script comments;
- generated route inventories in OpenAPI rather than handwritten lists.

This keeps the project page readable while retaining the evidence needed to manage the Rust transition.
