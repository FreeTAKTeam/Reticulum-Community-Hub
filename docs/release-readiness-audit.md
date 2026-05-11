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
| Rust core preserves Python-shaped domain behavior | `crates/r3akt-rch-core/src/lib.rs` tests | Core tests cover topics, clients, missions, teams, members, assets, skills, assignments, checklists, EAM, delivery policy, authorization, SQLite migration, and Python-shaped responses | Passed locally |
| TAK is a separate service, not embedded in `r3akt-rch-server` | `crates/r3akt-tak-connector/src/bin/r3akt-tak-service.rs`, packaging files | `r3akt-tak-service` bridges RCH telemetry/chat to TAK and TAK CoT to RCH marker routes through northbound HTTP; `r3akt-rch-server` does not own TAK socket lifecycle | Passed locally |
| Voice is an additional LXMF chat capability, not a voice-only destination class | `crates/r3akt-rch-server/src/lib.rs` tests | Voice-capable peer routing tests keep voice-capable identities in chat/fanout routing | Passed locally |
| Rust MSRV gate is valid for Rust 1.85 | `.github/workflows/rust.yml`, local `cargo +1.85.0` checks | Rust 1.85 clippy and workspace tests passed locally; fork CI run `25690105044` passed on Rust 1.85 | Passed |
| Release CI gate runs the committed verifier | `.github/workflows/rust.yml`, `scripts/release-readiness.ps1` | Fork CI run `25690707565` passed after updating checkout/setup-node actions to v6 | Passed |
| Server release binary builds and smokes | `scripts/release-readiness.ps1` | Release runner builds `r3akt-rch-server` and validates `/Status`, `/openapi.json`, `/Help`, and `/api/v1/app/info` against a temporary SQLite DB | Passed locally and in CI gate |
| Standalone TAK service release binary builds | `scripts/release-readiness.ps1`, packaging workflow | Release runner builds `r3akt-tak-service`; packaging and Tauri sidecar prep include the separate TAK service binary | Passed locally and in CI gate |
| Shared Vue UI remains buildable for Rust backend | `ui/`, `.github/workflows/rust.yml` | CI gate runs `npm --prefix ui ci`, lint, tests, and build through `scripts/release-readiness.ps1 -SkipDesktop` | Passed in CI gate |
| Desktop packaging keeps server and TAK sidecars separate | `apps/rch-desktop/`, packaging docs | Tauri sidecar prep builds/copies `r3akt-rch-server` and `r3akt-tak-service` separately | Passed locally; skipped in CI gate |
| Live Reticulum direct receipt and fanout work outside local unit mocks | `crates/r3akt-rch-server/src/lib.rs`, live env-gated tests | Local multi-daemon direct receipt and fanout validation are documented as passed; broader real-network Reticulum validation requires reachable `R3AKT_RETICULUMD_*` env vars | Blocked externally |
| Live TAK target profile works with the standalone service | `crates/r3akt-tak-connector/src/lib.rs`, `r3akt-tak-service` | Local TCP/UDP/TLS loopback and service bridge tests pass; `.\scripts\release-readiness.ps1 -LiveTak` now requires both outbound `R3AKT_TAK_LIVE_COT_URL` and inbound `R3AKT_TAK_LIVE_INBOUND_COT_URL`; configured target TAK attempts on 2026-05-11 were refused by the endpoint, and the Python-equivalent probe failed the same way | Blocked externally |

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
```

For a release candidate, also run the external live gates:

```powershell
.\scripts\release-readiness.ps1 -LiveTak -LiveReticulum
```

`-LiveTak` requires reachable TAK infrastructure for both directions through
`R3AKT_TAK_LIVE_COT_URL` and `R3AKT_TAK_LIVE_INBOUND_COT_URL`.

`-LiveReticulum` requires reachable Reticulum/LXMF peers through
`R3AKT_RETICULUMD_RPC_ENDPOINT`, `R3AKT_RETICULUMD_SOURCE`,
`R3AKT_RETICULUMD_RECEIPT_DESTINATION`, and
`R3AKT_RETICULUMD_FANOUT_DESTINATIONS`.

## Current Decision

Do not mark the Rust edition fully release-ready yet. The implementation passes
the current local and CI gates, but the release objective still depends on live
TAK target-profile validation and broader real-network Reticulum validation
outside the local multi-daemon harness.
