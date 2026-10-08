# Resource-stability evidence and task status

Updated 8 October 2026. The goal is **active and incomplete**. No sustained
acceptance, production recovery, release or publication is claimed here.

## Completed checkpoints

- RCH core commit `d63b626` skips serialization/upsert of unchanged command
  records. Two rollback/write-count regressions, all 90 core tests, three
  migration CLI tests and strict core Clippy passed. This removes unnecessary
  writes; broad command read snapshots and collection maps still need migration.
- Linux harness tests reject missing accounting, sampling gaps, warmup OOM or
  restart, idle delivery windows, hidden private-memory growth and forced
  shutdown. Generator deadlines include silence and partial lines. Cleanup is
  limited to owned random systemd units, preserves primary/cleanup failures,
  and verifies whole-cgroup termination before calling shutdown graceful.
- Effective controls were verified: two CPU affinities shared by RCH/daemon,
  daemon 512 MiB high / 768 MiB max / 2 GiB swap max, RCH 768 MiB high / 1 GiB
  max / 2 GiB swap max. Thirty-eight harness regressions and updated Linux preflight
  passed. The short real baseline verified both exit status zero and empty
  cgroups, with 95 SDK polls and zero poll errors.

- RCH command persistence commit `7b22448` removes an extra full core snapshot
  used only for marker/zone comparison. Twenty-two durability regressions and
  strict server Clippy passed. The remaining before/after transaction snapshots
  still require T8/T9 migration.
- The direct operation-right checkpoint moves all three permission-write
  adapters to one normalized keyed `IMMEDIATE` transaction. It reuses core
  validation, preserves grant UID, rejects corrupt key/payload disagreement,
  skips unchanged writes and commits before returning. The displaced permission
  write helper is removed; its remaining reader accepts only `&RchCore`.
  Six core and two router regressions cover rollback, deferred commit failure,
  competing connections, normalization, corruption, primary-key lookup and
  large unrelated malformed history. Independent correctness/maintainability
  review found no actionable issue; independent verification passed ten checks,
  including existing rights compatibility and broad-command concurrency.
  The committed server readiness runner passed strict workspace Clippy, 682
  tests (two explicit ignored tests), Rust docs, link checks, release build and
  HTTP smoke. Two initial new-code lint errors were corrected before the pass.
  `/tmp/rch-right-http1` verified 300 actual HTTP mutations against the immutable
  100,000-announce / 25,000-message fixture: 298 matching payload rows, 200
  changed writes and 100 zero-write repeats. Maximum decoded row payload was
  168 bytes; all unrelated history payload hashes stayed unchanged. Shutdown
  was graceful with an empty cgroup. This subsecond operation probe measures
  keyed payload accounting, not peak allocations or a memory plateau.
- Daemon PUSH/PULL diagnostics commit `ae950f8d` tracks dispatch, handler,
  queued-output and delivery work/bytes/time/outcomes through cancellation.
  Twenty ZeroMQ tests, three metric units, all 781 RPC library tests (eight
  explicit ignored diagnostics), strict RPC Clippy, module-size and issue369
  checks passed. Correctness/maintainer reviews and independent metric tests
  passed. This is accounting, not aggregate byte admission.
- Real SDK delivery preflight `/tmp/rch-delivery9` passed five unique messages
  each way, unchanged content, verified encryption/signatures, exact durable
  sender/receiver rows and terminal receipts. RCH completed 177 polls with zero
  errors; all three services exited zero with empty cgroups. Thirty-eight
  harness tests cover trickling replies, SDK setup/pipe failure and corrupted
  durable evidence. This short empty-history lane cannot pass final acceptance.
- Browser/CDP measurement preflight against the frozen release UI succeeded.
  One dashboard snapshot measured about 5.1 MB JavaScript heap and 2,996 DOM
  nodes. It does not establish chat navigation/backfill or a memory plateau.

The real-delivery checkpoint passed correctness/maintainer review. An independent
verifier reran all 38 harness regressions, revalidated all ten durable chains,
and checked runtime harness hashes. Review findings for startup cleanup,
whole-exchange deadlines, durable sender evidence and SQLite connection cleanup
were corrected before this checkpoint. The SDK peer is committed locally as
`299810fc`; no publication is implied.

## Attribution evidence, not acceptance

The immutable fixture has 135,893 signed/encrypted LXMF payloads (71,751,504
payload bytes), 1,000,000 durable associations across 940 histories, 100,000
RCH announces and 25,000 terminal RCH messages with 4 KiB content. Every wire
payload passed authenticated decryption and signature verification. Historical
stamp cost is zero; this does not qualify production stamp-mining cost.

| Experiment | SDK polls / errors | RCH RSS + swap, first / last minute median | Daemon RSS + swap, first / last minute median |
| --- | --- | --- | --- |
| Public preview.18, 600 s | 3,803 / 0 | 156.2 / 162.3 MiB | 111.2 / 179.1 MiB |
| Same fixture, diagnostic-only source, 600 s | 3,803 / 0 | 156.7 / 160.2 MiB | 109.0 / 126.8 MiB |
| Same fixture, durable inventory cutover, 600 s | 3,807 / 0 | 161.1 / 160.2 MiB | 48.1 / 58.7 MiB |

All three runs retained all payloads and approximately one million associations after
maintenance. Refilling and the local service peer legitimately change pending
counts. The differing memory increases show why one short run cannot prove the
production cause or a plateau. The first run also predates corrected shutdown
exit-status validation and cannot serve as shutdown acceptance evidence.

Diagnostic traversal borrows buffers rather than copying/serializing them. The
second run measured 52,874,496 owned peer-inventory buffer bytes initially,
remaining around 51.7 MB after maintenance. SDK event payload ownership was
under 180 KB at its end. These lower-level figures exclude allocator metadata,
map nodes, broadcasts, SQLite and transport allocations. They identify redundant
resident buffers without explaining the full production swap growth.

The cutover run retained 135,893 payloads and 1,000,457 associations across 941
histories, released inventory buffer capacity to zero throughout observation,
and verified both graceful exits and empty cgroups. Its 10-minute result supports
the partial inventory cutover; daemon anonymous memory still grew about 10 MiB,
so no plateau or final acceptance is claimed.

Raw local evidence is under `/tmp/rch-resource-stability/evidence/` and
`/tmp/rch-res-diag1/` and `/tmp/rch-res-fixed1/`, with binary, harness and fixture hashes in manifests.
Failed harness experiments remain recorded: an initial RPC framing error, an
overlong Unix socket path, incorrect identity/endpoint/capability setup and an
invalid 4 KiB inbound chat payload. None is attributed to the production incident.

## Current implementation board

| Task | Status and remaining evidence |
| --- | --- |
| T1 fixture/harness | Partial: valid large history and constrained sampling work; independent short real-delivery and browser measurement preflights pass; their integration with populated history, continuing browser load and operational transitions remains. |
| T2 attribution | Partial: owned inventory/event diagnostics and maintenance duration added; PUSH/PULL stage timing and wire-buffer ownership diagnostics implemented, with completed-output/unpolled-delivery cancellation tests; correctness/maintainer and independent metric review passed. Canonical ROUTER and full heap/byte admission remain. |
| T3 daemon ownership | Inventory cutover committed locally as `540e449a`; 781 RPC library tests and independent 14-test issue-657 verification pass. Correctness/maintainer reviews and same-fixture comparison pass for this partial checkpoint; no final stability claim. Aggregate byte limits remain. |
| T4 indexed migration (#256) | Pending historical-collision policy answer; no resolution policy selected. |
| T5 durable message APIs | Pending; SQLite must replace every resident-only reader/transition before eviction. |
| T6 bounded cache (#252) | Pending selected retention/active-work policy and T5. |
| T7 byte admission (#254) | Pending durable scheduling and selected active-work budget. |
| T8 command primitive (#255) | Partial: unchanged-write and direct operation-right keyed mutation/instrumentation checkpoints pass; generic keyed replay/read/write transactions and allocation evidence remain. |
| T9 all command families | Partial T9b: all three direct permission-write adapters moved; other rights/skill/moderation/log/change commands and every other family remain, including protocol, REM, common authorization/routing and inbound mission-sync callers. |
| T10 cancellation/shutdown (#257) | Pending real operation-stage cancellation, join ownership and non-cooperative dependency proof. Harness cleanup is not an application lifecycle fix. |
| T11 UI bounds (#253) | Pending chat cache/DOM bounds, durable paging, stale-fetch protection and browser evidence. Existing baseline source already contains config unmount guards and discovery single-flight polling. |
| T12 acceptance | Pending all preceding work, required repository gates and immutable >=3-hour representative real workload. |

The LXMF inventory cutover retains public legacy PeerRecord codec behavior, imports
legacy IDs once, frees buffers only after committed import, and serves explicit
inventories from SQLite. Tests cover failed import rollback/retry, completed
precedence, import/clear races, concurrent maintenance/completion, and zero buffer
capacity after release. Import and clear share `imports -> peers -> store` order.

Strict LXMF RPC Clippy now passes after formatting-only baseline corrections
in `29a39e14`. The new public-SDK driver also passes strict example Clippy
after equivalent formatting-only baseline SDK corrections. Required
full-workspace, daemon feature, UI and release-readiness gates
have not yet been completed for the overall goal.
