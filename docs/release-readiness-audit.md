# Rust Release Readiness Audit

This audit maps the Rust transition goal to concrete artifacts and evidence.
It is intentionally stricter than a green CI badge: the initial Rust alpha is
not release-ready until every required local, CI, server-package, ZeroMQ, REM,
and Reticulum gate is either passed or recorded as an explicit alpha risk.

Audit date: 2026-05-28

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
| Release CI gate runs the committed alpha verifier | `.github/workflows/rust.yml`, `scripts/release-readiness.ps1` | CI invokes `scripts/release-readiness.ps1 -ServerOnlyAlpha`, which excludes UI, desktop, and TAK service packaging from the alpha gate. The same committed alpha verifier passed locally on 2026-05-28 after LXMF-rs PR 207 merged into `origin/main` at `cbccf0f`. | Pending CI rerun |
| Server release binary builds and smokes with ZeroMQ configured | `scripts/release-readiness.ps1` | Alpha runner builds `r3akt-rch-server`, starts it with `--lxmf-zmq-command`, `--lxmf-zmq-response`, and `--reticulumd-source`, and validates `/Status`, `/openapi.json`, `/Help`, `/api/v1/app/info`, and `/diagnostics/runtime` against a temporary SQLite DB. This passed locally through `.\scripts\release-readiness.ps1 -ServerOnlyAlpha` on 2026-05-28 against LXMF-rs `origin/main` `cbccf0f`. | Passed locally |
| Server package contains only alpha artifacts | `.github/workflows/rust-release.yml`, `packaging/` | Release workflow packages the `r3akt-rch-server` binary plus server config/service helpers. It does not build or include UI assets, Tauri desktop artifacts, Electron, or `r3akt-tak-service` in the alpha server archive. | Passed by review; pending CI packaging run |
| ZeroMQ is the mandatory server-package southbound command transport | `crates/r3akt-transport-rns/src/lib.rs`, `crates/r3akt-rch-server/src/lib.rs`, live REM validation | RCH now runs outbound REM fanout through the LXMF-rs ZeroMQ SDK when `--lxmf-zmq-command`, `--lxmf-zmq-response`, and `--reticulumd-source` are configured. The SDK send request now carries LXMF-rs delivery options so REM `auto` messages are submitted as `method=propagated` and direct REM sends can request daemon propagation fallback. Optimized REM command channels are recorded as deferred outbound work (`dispatch_status=queued_deferred`) instead of blocking HTTP request handling on inline ZeroMQ dispatch. `git fetch origin` for LXMF-rs on 2026-05-28 left local `main` even with `origin/main` at `cbccf0f`; `cargo +1.85.0 test -p lxmf-sdk --features zmq-pipeline-backend -- --test-threads=1`, the four RCH package tests, and `.\scripts\release-readiness.ps1 -ServerOnlyAlpha` passed locally against that dependency state. | Passed for build/unit/package-smoke coverage against latest fetched LXMF-rs `origin/main`; live phone receipt still not proven |
| Live REM reduced-signature fanout works against connected phones | `docs/rem-southbound-interface.md`, `target/live-rem-validation/alpha-rem-patched-20260528-051549-*`, `target/live-rem-validation/alpha-rem-patched-20260528-062130-*`, `target/live-rem-validation/alpha-rem-patched-20260528-062524-*` local evidence | On 2026-05-28, two attached REM phones (`35031FDH2003N8`, `988b9b344135304639`) were available over ADB. Run `alpha-rem-patched-20260528-062130` proved the full reduced-signature field `9` matrix was serialized for two REM identities, but `/Control/Sync` ran before propagation-node discovery and returned 503. Run `alpha-rem-patched-20260528-062524` selected a propagation node successfully and reticulumd logged a propagated resource send for `sdk-zmq-2`, but RCH still ended with `message_count=28`, `queue_depth=28`, `reticulumd_dispatch_count=1`, `receipt_timeout_total=1`, `timeout_total=1`, and no final phone-side receipt. This proves reduced payload shape and daemon propagated-send handoff for at least one message; it does not prove end-to-end REM application on both phones. | Blocked for live phone receipt; reduced payload serialization passed |
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
  work. The latest 2026-05-28 runs `alpha-rem-patched-20260528-062130` and
  `alpha-rem-patched-20260528-062524` proved the reduced field `9` command
  shape is used for connected S8 and Pixelcorvo REM identities across the full
  checklist, EAM, log, marker, and telemetry matrix. They did not prove live
  phone receipt: the queue ended at depth 28 with zero final sent messages.
- RCH now passes LXMF-rs SDK delivery options through the ZeroMQ path. REM
  `auto` commands are submitted to the daemon as propagated sends after a
  propagation node is selected. The `alpha-rem-patched-20260528-062524` run
  logged a reticulumd propagated resource send, but the RCH queue still needs a
  follow-up run proving that all deferred REM messages drain successfully.
- LXMF-rs PR 207 fixed the previous daemon failure mode where one client
  disconnect stopped the reticulumd ZeroMQ RPC loop and is now merged in
  `origin/main` at `cbccf0f`. The local SDK changes required by RCH expose
  delivery method, stamp, ticket, and propagation-fallback options through both
  RPC and ZeroMQ SDK backends. The latest live run selected propagation nodes
  and handed one propagated resource to reticulumd, but did not observe a
  phone-side receipt.
- A passing two-phone delivery evidence run is still missing. Both attached
  phones were foregrounded over ADB and marked REM-capable for the latest run.
  The validator now proves EAM delete, marker unlink, log entry, checklist row
  delete, and telemetry serialization, but no message reached a final sent or
  delivered state.
- Latest LXMF-rs `reticulumd` expects TOML config, not the legacy Python
  Reticulum config syntax. The live runs using
  `target/live-rem-validation/reticulumd.toml` loaded the expected six
  interfaces and reproduced the link-activation/ZeroMQ response-drop blocker.
- ZeroMQ event polling is not a default release path yet. An experimental
  `R3AKT_ENABLE_ZMQ_EVENT_POLL=1` path exists for further daemon validation,
  but the 2026-05-27 no-RPC attempt caused reticulumd ZeroMQ RPC connection
  abort/timeouts. For the server package, keep HTTP RPC available for daemon
  event/receipt polling while ZeroMQ remains mandatory for outbound commands
  until the LXMF-rs ZeroMQ event stream is stable.

Next release-ready decision point: fix the remaining Reticulum link/queue
issue, then rerun the REM live matrix. The audit must be updated with a new run
ID and counters showing the connected-phone queue drains to zero.
