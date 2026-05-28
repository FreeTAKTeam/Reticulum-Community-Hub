# Rust Release Readiness Audit

This audit maps the Rust transition goal to concrete artifacts and evidence.
It is intentionally stricter than a green CI badge: the initial Rust alpha is
not release-ready until every required local, CI, server-package, ZeroMQ, REM,
and Reticulum gate is either passed or recorded as an explicit alpha risk.

Audit date: 2026-05-27

## Objective

Bring the Rust RCH server package to an initial alpha release state. This is a
server-package-only milestone, not the full stable 3.0 release.

## Success Criteria

| Requirement | Evidence artifact | Current evidence | Status |
| --- | --- | --- | --- |
| Preserve Python 2.9.x maintenance line separately from Rust work | `docs/rust-transition.md`, `rch-python` branch | `docs/rust-transition.md` names `rch-python` as the Python 2.9.6 maintenance branch and `rust-next` as the Rust edition | Passed |
| Rust server owns the northbound/UI-facing RCH contract | `crates/r3akt-rch-server/src/lib.rs`, OpenAPI route tests | `openapi_covers_python_northbound_route_inventory`, UI endpoint inventory tests, and HTTP/WebSocket route tests are in the server test suite | Passed locally and in CI gate |
| Python parity and Rust-required improvements are classified separately | `docs/release-contract-matrix.json`, `scripts/python-rust-parity.ps1`, `docs/release-parity-report.md` | Matrix labels `must-match-python`, `rust-additive-required`, and `intentional-difference`; generated report records baseline commits and separates Python-visible regressions from Rust-only release requirements such as REM compatibility and install-over-Python migration | Passed locally |
| Rust core preserves Python-shaped domain behavior | `crates/r3akt-rch-core/src/lib.rs` tests | Core tests cover topics, clients, missions, teams, members, assets, skills, assignments, checklists, EAM, delivery policy, authorization, SQLite migration, and Python-shaped responses | Passed locally |
| TAK is a separate service, not embedded in `r3akt-rch-server` | `crates/r3akt-tak-connector/src/bin/r3akt-tak-service.rs`, packaging files | `r3akt-tak-service` bridges RCH telemetry/chat to TAK and TAK CoT to RCH marker routes through northbound HTTP; `r3akt-rch-server` does not own TAK socket lifecycle | Passed locally |
| Voice is an additional LXMF chat capability, not a voice-only destination class | `crates/r3akt-rch-server/src/lib.rs` tests | Voice-capable peer routing tests keep voice-capable identities in chat/fanout routing | Passed locally |
| Rust MSRV gate is valid for Rust 1.85 | `.github/workflows/rust.yml`, local `cargo +1.85.0` checks | Rust 1.85 clippy and workspace tests passed locally; fork CI run `25690105044` passed on Rust 1.85 | Passed |
| Release CI gate runs the committed alpha verifier | `.github/workflows/rust.yml`, `scripts/release-readiness.ps1` | CI invokes `scripts/release-readiness.ps1 -ServerOnlyAlpha`, which excludes UI, desktop, and TAK service packaging from the alpha gate. The same committed alpha verifier passed locally on 2026-05-27. | Pending CI rerun |
| Server release binary builds and smokes with ZeroMQ configured | `scripts/release-readiness.ps1` | Alpha runner builds `r3akt-rch-server`, starts it with `--lxmf-zmq-command`, `--lxmf-zmq-response`, and `--reticulumd-source`, and validates `/Status`, `/openapi.json`, `/Help`, `/api/v1/app/info`, and `/diagnostics/runtime` against a temporary SQLite DB. This passed locally through `.\scripts\release-readiness.ps1 -ServerOnlyAlpha` on 2026-05-27. | Passed locally |
| Server package contains only alpha artifacts | `.github/workflows/rust-release.yml`, `packaging/` | Release workflow packages the `r3akt-rch-server` binary plus server config/service helpers. It does not build or include UI assets, Tauri desktop artifacts, Electron, or `r3akt-tak-service` in the alpha server archive. | Passed by review; pending CI packaging run |
| ZeroMQ is the mandatory server-package southbound command transport | `crates/r3akt-transport-rns/src/lib.rs`, `crates/r3akt-rch-server/src/lib.rs`, live REM validation | RCH now runs outbound REM fanout through the LXMF-rs ZeroMQ SDK when `--lxmf-zmq-command`, `--lxmf-zmq-response`, and `--reticulumd-source` are configured. The SDK call is isolated from Tokio runtime nesting and serialized so fanout clients do not contend for the same ZeroMQ response endpoint. RCH extends the ZeroMQ SDK request timeout to 300 seconds so live Reticulum link activation can return a daemon outcome instead of timing out on the client side first. | Passed for build/unit coverage; release-blocked on sustained live delivery/backlog |
| Live REM reduced-signature fanout works against connected phones | `docs/rem-southbound-interface.md`, `target/live-rem-validation/alpha-rem-300s-20260527-221119-*`, `target/live-rem-validation/alpha-rem-validcfg-20260527-232938-*` local evidence | On 2026-05-27, two attached REM phones (`35031FDH2003N8`, `988b9b344135304639`) were available over ADB. A clean single-message S8 marker probe on run `alpha-rem-timeout-20260527-215431` dispatched through reticulumd with `dispatch_accepted=1`, `sent=1`, `queue_depth=0`, and no ZeroMQ loop death after the timeout mitigation. The broader `alpha-rem-300s-20260527-221119` run persisted checklist create/upload/task add/style/cell/status/delete, EAM upsert/delete, marker create/link/unlink, mission forward-compatible change, and log-entry operations, but outbound delivery still ended with `outbound_enqueued_total=14`, `queue_depth=14`, `retry_total=14`, `timed_out_sends=1`, and daemon ZeroMQ loop stop. A fresh continuation run on 2026-05-27 using valid TOML reticulumd config and joined current REM clients (`alpha-rem-validcfg-20260527-232938`) confirmed the current blocker: reticulumd loaded six interfaces, accepted the S8 REM announce, RCH persisted checklist create/upload/task add reduced-signature commands for both S8 and Pixelcorvo, then S8 delivery failed at `link activation timed out` and reticulumd later logged `zmq rpc loop stopped: Codec Error: An established connection was aborted by the software in your host machine. (os error 10053)`. The full matrix did not reach row style/cell/status/delete/EAM/marker/log in that fresh joined-client run because the HTTP validation request timed out while the ZeroMQ SDK waited on the live delivery path. | Blocked |
| Live Reticulum direct receipt and fanout work outside local unit mocks | `crates/r3akt-rch-server/src/lib.rs`, `scripts/local-reticulum-live-gate.ps1`, live env-gated tests | `scripts/local-reticulum-live-gate.ps1` starts three temporary `reticulumd.exe` nodes and passed direct receipt plus two-recipient fanout on 2026-05-11; the same script also passed with `-ExternalConfigPath` against the local RMAP testnet config, using controlled temporary identities through public TCP hubs. This evidence predates the mandatory ZeroMQ/reduced-signature release validation and is no longer sufficient as final release evidence. | Needs refresh |
| Live TAK target profile works with the standalone service | `crates/r3akt-tak-connector/src/lib.rs`, `r3akt-tak-service` | Local TCP/UDP/TLS loopback and service bridge tests pass; `.\scripts\release-readiness.ps1 -LiveTak` requires both outbound `R3AKT_TAK_LIVE_COT_URL` and inbound `R3AKT_TAK_LIVE_INBOUND_COT_URL`; after the TAK server was restarted on 2026-05-11, `tcp://137.184.101.250:8087` passed live keepalive, reconnect, and bidirectional inbound relay validation | Passed against target profile |

## Required Release Gates

These gates must pass before declaring the Rust edition release-ready:

```powershell
cargo fmt --all -- --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace -- --test-threads=1
cargo test -p r3akt-rch-server
cargo test -p r3akt-rch-core
cargo test -p r3akt-transport-rns
cargo test -p r3akt-tak-connector
cargo build --release -p r3akt-rch-server
.\scripts\release-readiness.ps1 -ServerOnlyAlpha
.\scripts\local-reticulum-live-gate.ps1
.\scripts\local-reticulum-live-gate.ps1 -ExternalConfigPath <reticulumd-rmap-testnet.toml> -TimeoutSeconds 180 -DiscoverySettleSeconds 45 -ReceiptPollAttempts 240 -ReceiptPollDelayMs 1000
.\scripts\python-rust-parity.ps1 -RustBaseUrl <rust-url> -PythonBaseUrl <python-url>
```

For a release candidate, also run the external live gates when target
infrastructure is available:

```powershell
.\scripts\release-readiness.ps1 -LiveTak -LiveReticulum
```

`-LiveTak` requires reachable TAK infrastructure for both directions through
`R3AKT_TAK_LIVE_COT_URL` and `R3AKT_TAK_LIVE_INBOUND_COT_URL`. For clear TCP
targets without `R3AKT_TAK_LIVE_INBOUND_EXPECT_UID`, the inbound gate performs
an active bidirectional relay probe instead of depending on unsolicited CoT.

`-LiveReticulum` requires reachable Reticulum/LXMF peers through
`R3AKT_RETICULUMD_RPC_ENDPOINT`, `R3AKT_RETICULUMD_SOURCE`,
`R3AKT_RETICULUMD_RECEIPT_DESTINATION`, and
`R3AKT_RETICULUMD_FANOUT_DESTINATIONS`.

## Current Decision

The Rust edition is not ready for the stable 3.0 release yet.

Initial alpha release scope is intentionally narrowed to the server package.
Desktop/Tauri, Electron, shared UI packaging, and standalone TAK service
packaging are not alpha gates. ZeroMQ is mandatory for the southbound command
path. The reduced REM southbound interface is documented in
`docs/rem-southbound-interface.md` and remains optimized-only; no compatibility
payload is part of the release surface.

Open blockers:

- Fresh REM live validation is still not green after the reduced-signature
  work. Prior route-matrix attempts accepted checklist/EAM/marker/mission/log
  operations with optimized REM payloads, but live delivery backed up behind
  Reticulum link activation timeouts. The freshest joined-client run with a
  valid reticulumd TOML config only reached checklist create/upload/task add
  before the HTTP validation request timed out on the ZeroMQ live delivery path.
- The ZeroMQ SDK outbound boundary no longer panics inside Tokio, and a single
  S8 marker probe dispatched successfully after extending the SDK request
  timeout. Sustained matrix fanout still stops the reticulumd ZeroMQ loop after
  a live timeout, leaving queued messages and retry backlog.
- A passing two-phone evidence run is still missing. Pixelcorvo could be
  foregrounded over ADB and later logged a REM announce on-device, but the
  current RCH/reticulumd run did not produce a stable two-phone fanout with
  queue depth returning to zero.
- Latest LXMF-rs `reticulumd` expects TOML config, not the legacy Python
  Reticulum config syntax. The live run using `target/live-rem-validation/reticulumd.toml`
  loaded the expected six interfaces and reproduced the link-activation/ZMQ
  loop blocker.
- ZeroMQ event polling is not a default release path yet. An experimental
  `R3AKT_ENABLE_ZMQ_EVENT_POLL=1` path exists for further daemon validation,
  but the 2026-05-27 no-RPC attempt caused reticulumd ZeroMQ RPC connection
  abort/timeouts. For the server package, keep HTTP RPC available for daemon
  event/receipt polling while ZeroMQ remains mandatory for outbound commands
  until the LXMF-rs ZeroMQ event stream is stable.

Next release-ready decision point: rerun the server package gates and the REM
live matrix after the Reticulum link/queue issue is fixed, then update this
audit with the new run ID and counters.
