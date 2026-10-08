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

The populated real-delivery harness now has 68 passing regression tests,
including deadline-bound SQLite proofs, original-row preservation, maintenance
failure retention, cancellation cleanup, effective policy validation, OOM/process
identity checks and late discovery rejection. The SDK fixture explicitly activates
and announces its created identity and rejects a wrong identity/destination.
Strict SDK example Clippy, its focused test and release build pass. The separate
empty-history run `/tmp/rch-delivery13` passed five unique messages each way,
authenticated durable rows and terminal receipts, with zero poll errors and
three graceful shutdowns. This remains instrument qualification.
Independent verifier reran all 68 tests, revalidated all ten empty-run durable
chains and exact harness/binary/source hashes: 140 polls, zero errors, 21.87
seconds. Correctness/maintainer review and the separate identity checkpoint's
PRE review found no blocker or major finding.

Populated attempts remain failed evidence, with no observation/plateau claim:
`/tmp/rch-pop-delivery1` timed out during peer activation at the harness's old
10-second allowance and forced daemon shutdown. The established baseline already
allowed 120 seconds for this setup; attempts 2 and 3 completed activation in
57.39 and 59.86 seconds. They then failed the unchanged 30-second real-announce
discovery deadline. Attempt 3 learned the explicitly bound SDK service identity,
but the peer daemon did not learn RCH's registered destination despite repeated
successful `/Control/Announce` acknowledgements. All three services in attempts
2 and 3 shut down gracefully and source fixtures remained immutable. The cause
of the missing RCH network announcement is still under investigation.

The current fixture databases are cloned on tmpfs. These runs distinguish
process-private and cgroup memory accounting, but do not yet reproduce production
file-cache charging/reclaim: cloned pages may be charged to the harness/parent
rather than the daemon service. Final constrained acceptance requires regular
filesystem databases and scoped cold-page preparation, without global cache
dropping or changes to unrelated services.

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
| T2 attribution | Partial: owned inventory/event diagnostics, maintenance and PUSH/PULL stage timing/wire-buffer accounting pass. SDK failed-exchange method/session/stage correlation is committed locally and independently verified. RCH bootstrap-phase and daemon request/lock correlation, canonical ROUTER metrics and full heap/byte attribution remain. |
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

## Registered identity contract checkpoint

Local RCH commit `fc82358` keeps the public SDK's returned identity bundle with
its registered configuration. Registration/update require accepted activation
and accepted announce with the exact imported identity/destination before
publishing success; subsequent registered announces explicitly select that
identity without reimporting it. Standalone behavior and prior configuration
restoration on a new session remain unchanged. This does not prove why earlier
populated announces were not learned, and is not a memory fix.

Seven new contract regressions plus existing register/update/recovery tests
passed independent execution. The final server-readiness runner passed strict
workspace formatting/Clippy, 689 workspace/doc tests (two ignored), strict docs
and 57 links, release build and HTTP smoke. The exact frozen build then passed
empty-history real delivery attempts 14 and 15: ten distinct authenticated,
encrypted, durable message/receipt chains each, 140/141 polls with no errors,
and all three services exited gracefully. Attempt 15 uses the separately frozen
10-second announce cadence; both runs retain `passed_final_acceptance=false`.

## Populated discovery attribution and fixture correction

Attempt 4 failed local temporary-storage quota during activation; its result
file could not be written, so an external storage-failure record preserves the
exit status, explicit daemon quota error, immutable source hashes and absent
owned services. No delivery observation occurred. Stopped failed directories
1–6 are preserved on regular disk under the canonical workspace's ignored
`target/resource-stability-evidence/`, with symlinks retaining their original
`/tmp/rch-pop-deliveryN` paths. This relocation does not change the filesystem
model used while those experiments ran.

Attempts 5–7 each failed the original 30-second discovery deadline after 27
attempts. Existing sender traces in 6/7 show 28 RCH announce attempts including
startup, each with `SentBroadcast`, three matched/sent interfaces and no failed
interface. Receiver tracing in 7 shows 56 valid RCH packets held before the
inbound queue by ingress control for 298.23–359.78 seconds. The selected RCH
identity never became learned. All sources/hashes stayed intact and all owned
services exited gracefully. These are failed setup experiments, not memory or
delivery acceptance.

The harness's one-second periodic daemon announces were an artificial burst
source. A separately reviewed experiment freezes ten seconds in both daemon
launches and the manifest, preserving ingress control, manual SDK/RCH discovery,
all deadlines, 65 continuing pairs, maintenance, history and receipt gates.
All 69 harness regressions pass. Populated attempt 8 uses the same frozen
binaries and receive/send trace as attempt 7; discovery passed in 2.34 seconds.
Its eight-minute observation ended as failed evidence at the unchanged receipt
deadline: both receivers received all 65 unique payloads, both daemon stores
mark all 65 outgoing messages delivered, and 3,043 event polls had zero errors,
but RCH ended with only 27 delivered and 38 still sent. A successful maintenance
cycle pruned 34,908 pending associations, and subsequent traffic continued. The
final history/cardinality proof was not reached because receipt acceptance
failed; all three services exited gracefully and the source hashes stayed
unchanged. The cadence comparison supports the discovery-fixture correction,
not the production incident's cause or final resource stability.

The receipt mismatch is progressing backlog, not evidence of status expiry:
RCH's delivered count rose from 15 to 27 after sends stopped. Source review found
newest-first receipt scheduling with a four-RPC pass budget, plus guessed
`sdk-` ID probes before the actual message ID. At two new messages per ten-second
pass, those extra calls and initially unknown new sends can consume the budget
before older pending messages are revisited. This is a concrete amplification/
starvation lead; exact SDK binding and scheduler behavior require their own
reviewed checkpoint. Raw snapshot: `receipt-mismatch-snapshot.json` in attempt 8.

## SDK failed-exchange correlation checkpoint

Local LXMF commit `5a651d01` adds borrowed, call-local failure context with actual
method/session/request, stage, elapsed time, local send completion and a
saturating ignored-reply count. It annotates an SDK error once, keeps existing
semantic fields and details/extensions, and retains no successful-call registry,
logs, events or tasks. Context strings are bounded to 128 ASCII characters and
exclude parameters/authentication/endpoints/response contents/peer session IDs.
A colliding detail key remains unchanged with message-only local context.
Deadlines, resets and endpoint correlation behavior are unchanged. The existing
raw remote-error metadata loss in `map_rpc_error` is documented and deferred.

The final SDK suite passed 258 tests, with the live HTTP-vs-ZeroMQ stress test
ignored because it needs explicit live endpoints. Strict all-target SDK Clippy,
formatting, boundaries, module-size and the existing issue-369 source scanner
passed. Independent execution of all 75 ZeroMQ tests verified unchanged source
and binary hashes and no surviving owned test process group. The three exact
pre-existing formatting warnings were corrected separately in `a0361689`.
Frozen RCH/daemon experiments do not use this new SDK source; actual application
integration and operational recovery remain outstanding.
