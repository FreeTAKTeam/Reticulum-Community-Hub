# Priority delivery evidence — 11 November 2026

This records the local software evidence for [the plan](PLAN.md). The linked
pull requests retain the exact-head review, hosted checks and merge decisions.
Production deployment and sustained incident acceptance are separate gates.

## Delivered dependencies

| Issue | Pull request | Reviewed head | Merge |
|---|---|---|---|
| RCH #231 | [RCH #320](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/pull/320) | `4663db22bb91be68b83e09bd9ed71e004fe0df4e` | `8ed62c8f3faac3a4fc09081962a5a3ddfa09a887` |
| LXMF #755 | [LXMF #756](https://github.com/FreeTAKTeam/LXMF-rs/pull/756) | `85566f1cf01aeb8da6856e77a03335f561fd0f1c` | `460fef80eeff371500965d2331856bf67a407387` |

Both issues closed on merge. RCH #320 passed all 13 hosted checks. LXMF #756
passed all applicable checks, including the protected `CI required`,
`HIL PR level` and `evidence (rns-rs)` contexts; publishing was intentionally
skipped. No branch protections were changed.

RCH #320 adds nonmutating startup warnings for valid legacy password/PIN
records and preserves upgrade on successful verification. Tests cover both
legacy kinds, current/malformed/absent records, unchanged stored fields and the
exact anonymous post-enrollment setup response. An isolated HTTP run confirmed
warnings, password migration and PIN-only warning after restart. The cited
environment example, setup redaction and PostCSS findings were already fixed.

LXMF #756 expires abandoned negotiated sessions after five idle minutes, keeps
accepted in-flight requests pinned and exposes current/expired counts. Durable
identities, messages, checkpoints and idempotency survive expiry. Deterministic
coverage includes 8,188 abandoned routes, live capacity and principal isolation.
The final upstream workspace run passed 4,294 tests with 305 ignored across 151
binaries; the explicitly selected real ZeroMQ expiry gate also passed in
301.27 seconds. Strict Clippy, architecture and security gates passed.

Both PRs precisely update rustix 1.1.4 to 1.1.6 for
[RUSTSEC-2026-0486](https://github.com/rustsec/advisory-db/blob/main/crates/rustix/RUSTSEC-2026-0486.md),
without suppressing the advisory or changing unrelated Windows dependencies.

## Final RCH pair

The integration source under test is RCH
`41f4dbb8f3e642968c38c931804b09beb619f3b8`, including RCH #320. Subsequent changes
in this delivery record are documentation only. Its four Cargo dependencies,
eight Git lock entries, three workflow `LXMF_REF` values and runtime manifest
all identify merged LXMF revision `460fef80eeff371500965d2331856bf67a407387`.
Locked Cargo metadata resolved successfully. SDK version remains 0.16.1 and no
release tag is asserted.

The daemon was rebuilt from that merged revision with `zmq-pipeline-rpc`.
The generated Linux debug binaries used for the standalone gate have SHA-256:

| Binary | SHA-256 |
|---|---|
| `r3akt-rch-server` | `61c7c8c0db176dcbf0a7f3daae7cf138a0876b6b8992024a8a273d64a7c9e513` |
| `rch_identity_report` | `8857bc808b6d2272a7385469d3f904e7179ff45ba6068b94722317f244a995cc` |
| `reticulumd` | `b32869a3ece0f4d3eb3bde8b87905bb7ddecb7297c5c0a61d25b27477e8b567b` |

### Same actor recovery

Run the committed regression explicitly; normal suites ignore its five-minute
wall-clock wait:

```sh
cargo +1.99.1 test --locked -p r3akt-rch-server --lib \
  durable_broker::tests::recovery::paired_rch_actor_recovers_expired_session_and_durable_custody \
  -- --exact --ignored --nocapture
```

The test uses the pinned RPC daemon over real framed ZeroMQ with generated local
state. Three closed actors and one idle actor expire while a fifth actor remains
active. It requires `SDK_BROKER_NEGOTIATION_REQUIRED`, then starts the production
worker on the same idle actor and gives recovery eight seconds. The original
journal/consumer survives; local stored/applied and daemon-acknowledged custody
advance from 1 to 2, exactly two messages exist, and session counts finish at
2 current / 4 expired. No new retry owner or adapter behavior was needed.

Passed: **1 test, 301.25 seconds** against the final pin. Best-effort actor
Drop reports a closed shutdown channel after the test explicitly shuts actors
down; the test and custody assertions pass.

### Standalone restart and peer delivery

A retained local probe launches the actual RCH server plus two source-matched
daemon processes on loopback with generated identities/databases. One daemon
stays running across three graceful SIGINT exits and three abrupt SIGKILL exits
of RCH, for seven RCH incarnations. Each of the six intervening messages is sent
while RCH is down and must receive a sender-side delivered receipt before RCH
restarts. Each restarted server must then apply the next durable event.

The probe asserts a stable daemon PID and journal and checkpoints 1 through 7.
It observes seven sessions before expiry and asserts reclamation to 1 current /
6 expired while the last server stays active, then one more peer receipt and
checkpoint 8. It also checks the child processes remain alive and scans their
logs for the specific `memory allocation of` abort signature. These are short
debug-process observations, not a memory ceiling or soak.

Passed: **8 sender receipts**, checkpoint **8 stored / 8 applied**,
**1 current / 6 expired** sessions. Sampled RSS was **71,544–72,832 KiB** for
RCH and **124,772–130,280 KiB** for the hub daemon. The separate peer is not
included in these RSS ranges.

The retained `rch-307-standalone-probe.py` is invoked with the absolute server
and daemon executable paths as its two arguments. Its SHA-256 is
`fe987548e083b9385906dca3ff54c39dbf500bdb7daba88f7f99dfb8f51277c6`;
the server's sibling `rch_identity_report` supplies the generated identity's
public delivery destination.

### Multi-node delivery

The committed runner is exercised with a small real local workload:

```sh
pwsh -NoProfile -File scripts/local-reticulum-live-gate.ps1 \
  -RustToolchain 1.99.1 -ReticulumdExe /tmp/rch-307-durable-daemon \
  -ZmqLoadOnly -LoadMessages 12
```

The local executable wrapper only prepends `--zmq-durable-broker` to the matched
daemon command, because the runner does not otherwise enable that mode. This
path must execute a nonzero test count and confirm receipt at both receivers.
The runner's historical direct/fanout/event-poll filters currently match zero
tests and are not counted as evidence. Direct sender receipts are covered by
the separate standalone probe above.

Passed: **1 selected test, 12 requested / 12 accepted / 12 received**, with
**6 messages per receiver**. The receipt-complete portion took 0.897 seconds;
this tiny workload is a delivery check, not a load/performance qualification.

## Local checks and review

Rust 1.99.1 uses locked dependencies. This host requires
`OPENSSL_LIB_DIR=/usr/lib/x86_64-linux-gnu` and
`CFLAGS=-I/usr/include/x86_64-linux-gnu` for native OpenSSL discovery.

```sh
cargo +1.99.1 fmt --all -- --check
cargo +1.99.1 clippy --locked --workspace --all-targets -- -D warnings
cargo +1.99.1 test --locked --workspace -- --test-threads=1
cargo +1.99.1 build --locked -p r3akt-rch-server --bins
pwsh -NoProfile -File scripts/check-doc-links.ps1
pwsh -NoProfile -File scripts/check-rust-module-size.ps1
git diff --check
```

Passed: **801 tests, 0 failures, 3 ignored** in the normal workspace run. The
ignored expiry test is executed separately above. This includes server (356
library tests plus 30 binary tests), core (131), transport (64) and TAK (61
library plus 21 binary tests); these counts are subsets of 801, not additional
tests. The existing `issue_307_count_is_rejected_before_allocation` and
`zmq_announce_sweeps_skip_malformed_capabilities_and_replay_after_restart`
regressions both passed. Formatting, strict workspace Clippy, debug binary
builds, module budgets and local document links passed. Release builds, MSRV,
dependency audit and the rest of hosted CI remain required before merge.

Independent SOL POST review of `41f4dbb` found no correctness or maintainability
blockers: all pins agree, historical evidence retains its source attribution,
and the recovery assertion checks daemon-persisted custody rather than only a
local checkpoint. The parent separately reviewed the process probe and final
scope. Final hosted checks and merge authorization are recorded on the
integration PR; this local record does not substitute for them.

GitHub rejected author self-approval for this account. Independent technical
reviews are recorded as COMMENT reviews; they are not represented as GitHub
APPROVED reviews, and no protection bypass or alternate identity is used.

## Remaining acceptance

- [RCH #307](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/issues/307)
  remains open for sustained operational acceptance. The already-merged #310
  parser repair is retained and exercised by the workspace regression suite;
  no private crash data was accessed and no production deployment occurred.
- [RCH #241](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/issues/241),
  [RCH #242](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/issues/242) and
  [LXMF #663](https://github.com/FreeTAKTeam/LXMF-rs/issues/663) retain their broader
  resource, long-running and operational gates. Radio, physical clients, live
  TAK and published installer qualification were not run.
- Reaping remains lazy at admission, diagnostics or requests. All-live capacity
  still returns busy. Ordinary unnegotiated methods retain their documented
  behavior if another call already reaped the entry; durable calls require
  restoration. No new close API or tombstone registry was introduced.
- Runtime logs and the standalone probe are kept as local task artifacts;
  generated databases, identity keys and runtime outputs are not committed.
