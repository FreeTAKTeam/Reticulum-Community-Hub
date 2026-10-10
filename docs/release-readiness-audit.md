# Rust Release Readiness Audit

This audit maps the Rust transition goal to concrete artifacts and evidence.
It is intentionally stricter than a green CI badge: the initial Rust alpha is
not release-ready until every required local, CI, server-package, ZeroMQ, REM,
and Reticulum gate is either passed or recorded as an explicit alpha risk.

Audit date: 2026-06-22; preview.10 supplement: 2026-08-13;
LXMF dependency supplement: 2026-09-30

The table retains historical evidence. Current preview.11 findings, validation,
limitations, and artifact identity are tracked in
[`stabilization-v3.0.0-preview.11.md`](stabilization-v3.0.0-preview.11.md).
The [preview.10 report](stabilization-v3.0.0-preview.10.md) records the earlier release.

## Issue #238 development baseline

Development dependencies and CI now use LXMF-rs `0.13.0` plus the ZeroMQ
connection/response, restart-cursor recovery and storage-contention reactor fixes plus the indexed propagation-mark lookup for #242 and memory/disk/poll-lock corrections for LXMF-rs #655 and bounded propagation queues/inventory allocations for #657, durable inventory ownership, projected poll metadata and call-local failed-exchange diagnostics, durable ZeroMQ custody, generation-aware reply-connection reuse and retained delivery-stage failures at `a424760137c7eaee5d5de7fb9ef2347871b85da1`.
This includes a daemon response-writer fix; pairing the new RCH SDK with an
unpatched old daemon does not provide the complete fix. See
[the issue evidence](issue-238-inbound-zmq.md) for fresh validation and limits.
The preview.11 release evidence below remains a historical record.

## Issue #242 development qualification

The current source adds bounded announce imports/diagnostics and schema-4
projections, plus the pinned daemon propagation-mark index. See
[resource evidence and upgrade instructions](issue-242-resource-efficiency.md).
This development qualification does not supersede the published preview.12
artifact record or establish production resolution under a 2 GiB memory limit.
The matching preview.13 publication is described in
[its release notes](release-notes-v3.0.0-preview.13.md); package acceptance
requires successful builds and independent public-download verification.

## Linux AMD64 testing scope

The existing release workflow supports Linux AMD64 server-only testing
candidates, as documented in [packaging instructions](../packaging/README.md).
The scope changes platform selection, not the package contents or validation
requirements. The archive still includes the pinned daemon, UI, and TAK service.
The Linux daemon service template enables `--zmq-durable-broker` for fresh
databases. Verify its public checksum, embedded source identities, and runtime smoke
before reporting package acceptance. Production memory, swap, and reply-delay
acceptance remains a separate test on the affected host.

## LXMF-rs v0.12.0 Integration (preview.11 historical)

The preview.11 dependency, CI, and packaged-daemon baseline was LXMF-rs `v0.12.0`
at commit `20717f4456d1b402bcc3cb7e8a1a3a86c9bb4755`. Its lockfile resolved
`lxmf-reference`, `lxmf-wire`, `lxmf-sdk`, `reticulum-rs-core`, and
`reticulum-rs-rpc` to `0.12.0`. The runtime manifest records SDK contract
release `v2.6` and the identity import, activation, and discovery operations
required by RCH's service identity registration.

The initial dependency-only integration validation used a clean checkout of that immutable release while
preserving the existing modified sibling checkout. Formatting, denied-warning
workspace clippy, all 564 workspace tests, the four focused backend crate
suites, the locked Rust 1.85 check, denied-warning Rust documentation, module
size and documentation link checks, and `cargo audit --deny warnings` passed.
The matching ZeroMQ-capable daemon also passed a locked Rust 1.88 check.
The standard workspace run leaves the infrastructure-dependent load test
ignored; the local harness ran it explicitly.

The committed `scripts/release-readiness.ps1 -ServerOnlyAlpha` gate also passed,
including the optimized server build and HTTP smoke for `/Status`,
`/diagnostics/runtime`, OpenAPI, help, and application information.

The Linux server archive and Tauri AppImage built successfully. The server
archive checksum, embedded LXMF release/commit and SDK contract metadata, and
daemon checksum were verified. The prepared desktop sidecar hash matches the
clean-release build. AppImage bundling rewrites its loader search path to
`$ORIGIN/../lib`; the extracted daemon's executable code and data sections match
the clean-release binary, with differences confined to that loader metadata.

Direct Cargo and desktop commands used the Linux OpenSSL multiarch include
and library settings that the readiness runner discovers automatically.

The local three-daemon harness passed direct receipts, two-recipient fanout,
ZeroMQ event polling, and a 500-message batch run with 500 accepted and 500
received, split 250/250 across two receivers. The
[load test](../crates/r3akt-rch-server/src/lxmf_load_tests.rs) now imports and
activates a service identity in each sender and receiver SDK session before
using its delivery destination. This follows the session ownership checks in
the new daemon; the production RCH path already registers its service identity.

This supplement records the initial local software integration before the
preview.11 hardening changes. The candidate report owns its fresh qualification.
Hosted CI, other platform
packages, and external or physical-device acceptance retain their separate
release gates.

## Objective

Bring the Rust RCH server package to an initial alpha release state. This is a
server-package-only milestone, not the full stable 3.0 release.

## Success Criteria

| Requirement | Evidence artifact | Current evidence | Status |
| --- | --- | --- | --- |
| Preserve Python 2.9.x maintenance line separately from Rust work | `docs/rust-transition.md`, `rch-python` branch | `docs/rust-transition.md` names `rch-python` as the Python 2.9.6 maintenance branch and `rust-next` as the Rust edition | Passed |
| Rust server owns the northbound/UI-facing RCH contract | `crates/r3akt-rch-server/src/lib.rs`, OpenAPI route tests | `openapi_covers_python_northbound_route_inventory`, UI endpoint inventory tests, and HTTP/WebSocket route tests are in the server test suite | Passed locally and in CI gate |
| Python parity and Rust-required improvements are classified separately | `docs/release-contract-matrix.json`, `scripts/python-rust-parity.ps1`, `docs/release-parity-report.md` | Matrix labels `must-match-python`, `rust-additive-required`, and `intentional-difference`; generated report records baseline commits and separates Python-visible regressions from Rust-only release requirements such as REM compatibility and install-over-Python migration. A live two-server parity probe passed on 2026-06-22 against Rust `http://127.0.0.1:18180` and Python `http://127.0.0.1:18181`: Rust OpenAPI had no failed route probes for the matrix scope, and Python OpenAPI had no failed route probes for must-match route contracts. Rust-only control, streaming, and `/openapi.yaml` routes are now classified as Rust-additive HTTP routes instead of Python-required routes. | Passed locally |
| Rust core preserves Python-shaped domain behavior | `crates/r3akt-rch-core/src/lib.rs` tests | Core tests cover topics, clients, missions, teams, members, assets, skills, assignments, checklists, EAM, delivery policy, authorization, SQLite migration, and Python-shaped responses | Passed locally |
| TAK is a separate service, not embedded in `r3akt-rch-server` | `crates/r3akt-tak-connector/src/bin/r3akt-tak-service.rs`, packaging files | `r3akt-tak-service` bridges RCH telemetry/chat to TAK and TAK CoT to RCH marker routes through northbound HTTP; `r3akt-rch-server` does not own TAK socket lifecycle | Passed locally |
| Voice is an additional LXMF chat capability, not a voice-only destination class | `crates/r3akt-rch-server/src/lib.rs` tests | Voice-capable peer routing tests keep voice-capable identities in chat/fanout routing | Passed locally |
| Rust MSRV gate is valid for Rust 1.85 | `.github/workflows/rust-pr-quality.yml`, local `cargo +1.85.0` checks | PR quality control has a dedicated Rust 1.85 locked workspace check plus denied-warning rustdoc; Rust 1.88 remains the normal release toolchain. Historical `Rust workspace` run `26696071362` passed the committed gate on commit `8dc69773af38ced251138c007c6f0bdc9543ea02`. | Dedicated workflow defined; preview.9 run pending |
| PR Rust quality control is explicit and branch-protectable | `.github/workflows/rust-pr-quality.yml` | Pull requests into `rust-next` or `main` get separate checks for `cargo fmt --all -- --check`, `cargo clippy --workspace --all-targets -- -D warnings`, `cargo test --workspace -- --test-threads=1`, release builds for `r3akt-rch-server` and `r3akt-tak-service`, and `cargo audit --deny warnings`. The workflow is branch-protectable; current push evidence is provided by the stricter committed alpha gate in `Rust workspace` run `26696071362`. | Workflow defined; push gate passed |
| Release CI gate runs the committed alpha verifier | `.github/workflows/rust.yml`, `scripts/release-readiness.ps1` | CI invokes `scripts/release-readiness.ps1 -ServerOnlyAlpha`, which runs Rust format, clippy, workspace tests, the server release build, and the ZeroMQ-configured release HTTP smoke. `Rust workspace` run `26696071362` passed on commit `8dc69773af38ced251138c007c6f0bdc9543ea02`. | Passed in CI |
| Server release binary builds and smokes with ZeroMQ configured | `scripts/release-readiness.ps1` | Alpha runner builds `r3akt-rch-server`, starts it with `--lxmf-zmq-command`, `--lxmf-zmq-response`, and `--reticulumd-source`, and validates `/Status`, `/openapi.json`, `/Help`, `/api/v1/app/info`, and `/diagnostics/runtime` against a temporary SQLite DB. This passed locally through `.\scripts\release-readiness.ps1 -ServerOnlyAlpha` on 2026-05-28 against LXMF-rs `origin/main` `cbccf0f`. The Rust workspace baseline on 2026-07-18 targeted LXMF-rs `v0.9.5` commit `7cafc5b4be21ff4f777d0f2300cfb79e5d0da23c`; on 2026-07-18, `cargo fmt --all -- --check`, `cargo clippy --workspace --all-targets -- -D warnings`, `cargo test --workspace`, and the focused release-critical crate tests passed against that baseline. Earlier release-build and local workflow-YAML checks passed before publishing `v3.0.0-preview.2` against the prior `v0.5.0` baseline. | Passed locally |
| Full Rust release packaging mirrors Python release artifact flow | `.github/workflows/rust-release.yml`, `scripts/build-rust-release-package.ps1`, `packaging/`, `apps/rch-desktop/` | Rust release packaging supports manual workflow artifacts and published-release asset attachment. `Build Rust Release Packages` run `26696071364` passed on commit `8dc69773af38ced251138c007c6f0bdc9543ea02`, producing Linux and Windows server archives plus Linux AppImage and Windows NSIS desktop artifacts. The workflow now also defines macOS x64, macOS arm64, and Linux Raspberry Pi 64 server archive jobs for the next release/manual run. | Passed in CI for prior matrix; expanded matrix needs next run |
| Release packages carry traceable version metadata | `.github/workflows/rust-release.yml`, `scripts/build-rust-release-package.ps1`, `release-manifest.json` inside the server archive | Server archive names include the resolved release version from the GitHub release tag, pushed tag, manual workflow input, or branch ref. The green `rust-next` packaging run produced `rch-rust-full-windows-x64-rust-next.zip` and `rch-rust-full-linux-x64-rust-next.tar.gz`; both downloaded manifests record `release_version=rust-next`, `git_ref=rust-next`, `git_sha=8dc69773af38ced251138c007c6f0bdc9543ea02`, and inclusion of server, TAK service, and UI payloads. The expanded matrix keeps the same naming and manifest path for Windows x64, macOS x64, macOS arm64, Linux AMD64, and Linux Raspberry Pi 64 packages. | Passed in CI for prior matrix; expanded matrix needs next run |
| ZeroMQ is the mandatory server-package southbound command transport | `crates/r3akt-transport-rns/src/lib.rs`, `crates/r3akt-rch-server/src/lib.rs`, live REM validation | RCH runs outbound REM fanout through the LXMF-rs ZeroMQ SDK envelope protocol when `--lxmf-zmq-command`, `--lxmf-zmq-response`, and `--reticulumd-source` are configured. Optimized REM command channels use the ZeroMQ path without reintroducing RPC compatibility. The committed alpha verifier passed in CI on 2026-05-30, and the later live REM bridge fix maps `auto` to daemon params `method=direct` plus `try_propagation_on_fail=true` so current `reticulumd` receives the intended direct-with-propagation-fallback instruction. | Passed in CI and live validation |
| Live REM reduced-signature fanout works against connected phones | `docs/rem-southbound-interface.md`, `docs/release-live-stress-report.md` | Earlier 2026-05-28 runs proved the reduced field `9` command shape across checklist, EAM, log, marker, and telemetry payloads but did not prove phone receipt. The later live retest documented in `docs/release-live-stress-report.md` created online checklist `RCH TCP aligned REM checklist 162257`; `/Events` showed `recipient_count=2`, `sent=2`, and `command_type=checklist.create.online`; reticulumd traces showed both Noemi and Pixel messages reaching `sent: link resource`; Pixel 7 and Pixel 8a screenshots showed the checklist at the top of REM Checklists. | Passed live for two-phone checklist fanout |
| Live Reticulum direct receipt, fanout, ZeroMQ event polling, and local ZeroMQ load work outside local unit mocks | `crates/r3akt-rch-server/src/lib.rs`, `scripts/local-reticulum-live-gate.ps1`, live env-gated tests | `scripts/local-reticulum-live-gate.ps1 -IncludeZmqEventPoll -IncludeZmqLoad -DiscoverySettleSeconds 10 -ReceiptPollAttempts 180` passed locally on 2026-06-22. The refreshed gate starts three temporary `reticulumd.exe` nodes, verifies direct receipt and two-recipient fanout through the outbound worker path, polls `sdk_poll_events_v2` over the LXMF-rs ZeroMQ RPC loop, then runs a 500-message chunked `sdk_send_batch_v2` load check with 500 accepted and 500 received across two receiver daemons. A heavier local stress run also passed on 2026-06-22 with `-ZmqLoadOnly -NodeCount 5 -LoadReceiverCount 4 -LoadMessages 1000 -LoadSenderClients 4 -DiscoverySettleSeconds 10 -LoadPollAttempts 480 -LoadPollDelayMs 250`, delivering 1000 accepted and 1000 received messages evenly across four receiver daemons. A live-device RC stress pass on 2026-06-22 found two USB Columba phones (`Pixel_7`, `SM_G950W`) plus announced `silkedeck` and `corvodeck` peers; `raphydeck` was not present in the current 5,000-row announce cache. The first propagated canary exposed a daemon/RPC hang from an unbounded bridge connect; after bounding bridge connects, one canary and a 25-message bounded run to the phone/deck targets posted 25/25 successfully, with RCH diagnostics reporting 26 accepted propagated dispatches, zero dispatch failures, zero stuck futures, and zero send timeouts. The same script still supports `-ExternalConfigPath` for controlled RMAP testnet validation, but that external profile has not been rerun after this refresh. | Passed locally and live-device dispatch; external RMAP refresh still useful |
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
cargo +1.85.0 check --workspace --all-targets --locked
cargo audit --deny warnings
$env:RUSTDOCFLAGS = "-D warnings"; cargo doc --workspace --no-deps
npm --prefix ui ci
npm --prefix ui run lint
npm --prefix ui run typecheck
npm --prefix ui run test
npm --prefix ui run build
cargo build --release -p r3akt-rch-server
.\scripts\release-readiness.ps1 -ServerOnlyAlpha
.\scripts\local-reticulum-live-gate.ps1 -IncludeZmqEventPoll -IncludeZmqLoad -DiscoverySettleSeconds 10 -ReceiptPollAttempts 180
.\scripts\local-reticulum-live-gate.ps1 -ZmqLoadOnly -NodeCount 5 -LoadReceiverCount 4 -LoadMessages 1000 -LoadSenderClients 4 -DiscoverySettleSeconds 10 -LoadPollAttempts 480 -LoadPollDelayMs 250
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

The initial alpha release scope is the Rust server/package line, with desktop
bundles treated as preview artifacts. The server alpha gates are now green on
commit `8dc69773af38ced251138c007c6f0bdc9543ea02`: the committed Rust 1.85
`ServerOnlyAlpha` verifier passed in CI, full release packaging passed in CI,
downloaded server and desktop artifacts passed checksum verification, and live
two-phone REM checklist fanout is documented as delivered and visible in both
REM phone UIs.

No current local server-alpha blocker is recorded in this audit. Remaining work
before stable `v3.0.0`:

- Run the external RMAP Reticulum profile again after the latest ZeroMQ event
  polling refresh, if public testnet evidence is required for the release notes.
- Publish a tagged preview or alpha release so the packaging workflow embeds a
  semantic release tag such as `v3.0.0-preview.4` instead of the staging branch
  label `rust-next`.
- Continue broad parity hardening for less common Python edge cases listed in
  `README.md` and `docs/release-contract-matrix.json`.

## Preview.12 matching testing publication

The user authorized a matching RCH testing prerelease after the standalone
reticulumd rch241.2 publication. [Preview.12 release notes](release-notes-v3.0.0-preview.12.md)
record the paired source and deployment scope. Backend source is unchanged
from the qualified issue #241 pair. The existing release workflow must build
all five server and two desktop packages at the new source tag before package
readiness is claimed. Public download checksums, all server source manifests
and fresh downloaded Linux inbound persistence are publication acceptance;
native desktop interaction and the original production trigger remain separate
unproven acceptance. This does not change the stable-release gates above.
