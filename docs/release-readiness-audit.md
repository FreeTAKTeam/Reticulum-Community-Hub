# Rust Release Readiness Audit

This audit maps the Rust transition goal to concrete artifacts and evidence.
It is intentionally stricter than a green CI badge: Rust is not release-ready
until every required local, CI, package, UI, TAK, and Reticulum gate is either
passed or explicitly waived for a preview release.

Audit date: 2026-05-11

## Objective

Finish functional parity work between the Python and Rust RCH implementations so
the Rust implementation is fully functional and ready for release.

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
| Release CI gate runs the committed verifier | `.github/workflows/rust.yml`, `scripts/release-readiness.ps1` | Fork CI run `25690707565` passed after updating checkout/setup-node actions to v6 | Passed |
| Server release binary builds and smokes | `scripts/release-readiness.ps1` | Release runner builds `r3akt-rch-server` and validates `/Status`, `/openapi.json`, `/Help`, and `/api/v1/app/info` against a temporary SQLite DB | Passed locally and in CI gate |
| Standalone TAK service release binary builds | `scripts/release-readiness.ps1`, packaging workflow | Release runner builds `r3akt-tak-service`; packaging and Tauri sidecar prep include the separate TAK service binary | Passed locally and in CI gate |
| Shared Vue UI remains buildable for Rust backend | `ui/`, `.github/workflows/rust.yml` | CI gate runs `npm --prefix ui ci`, lint, tests, and build through `scripts/release-readiness.ps1 -SkipDesktop` | Passed in CI gate |
| Desktop packaging keeps server and TAK sidecars separate | `apps/rch-desktop/`, packaging docs | Tauri sidecar prep builds/copies `r3akt-rch-server` and `r3akt-tak-service` separately | Passed locally; skipped in CI gate |
| Live Reticulum direct receipt and fanout work outside local unit mocks | `crates/r3akt-rch-server/src/lib.rs`, `scripts/local-reticulum-live-gate.ps1`, live env-gated tests | `scripts/local-reticulum-live-gate.ps1` starts three temporary `reticulumd.exe` nodes and passed direct receipt plus two-recipient fanout on 2026-05-11; the same script also passed with `-ExternalConfigPath` against the local RMAP testnet config, using controlled temporary identities through public TCP hubs | Passed locally and against controlled external RMAP profile |
| Live TAK target profile works with the standalone service | `crates/r3akt-tak-connector/src/lib.rs`, `r3akt-tak-service` | Local TCP/UDP/TLS loopback and service bridge tests pass; `.\scripts\release-readiness.ps1 -LiveTak` requires both outbound `R3AKT_TAK_LIVE_COT_URL` and inbound `R3AKT_TAK_LIVE_INBOUND_COT_URL`; after the TAK server was restarted on 2026-05-11, `tcp://137.184.101.250:8087` passed live keepalive, reconnect, and bidirectional inbound relay validation | Passed against target profile |

## Required Release Gates

These gates must pass before declaring the Rust edition release-ready:

```powershell
cargo fmt --all -- --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace -- --test-threads=1
cargo build --release -p r3akt-rch-server
cargo build --release -p r3akt-tak-connector --bin r3akt-tak-service
npm --prefix ui ci
npm --prefix ui run lint
npm --prefix ui run test
npm --prefix ui run build
.\scripts\release-readiness.ps1 -SkipDesktop
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

The Rust edition is ready for a Rust preview release. The current evidence
covers local, CI, package, UI, TAK target-profile, local Reticulum
multi-daemon, and controlled external RMAP Reticulum gates. Keep final
default-branch cutover gated on the broader project decision to replace the
Python line, but no functional parity release blocker remains in this audit.
