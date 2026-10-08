# Sustained RCH and daemon resource stability implementation plan

**Intent:** Resolve RCH #252–#257 and LXMF-rs #657, including the recurring daemon memory-plus-swap growth observed after preview.18. Completion requires sustained representative runtime evidence.
**Current Behavior:** RCH hydrates and duplicates historical messages, commands load broad aggregates and rewrite unchanged payloads, queues have item-only limits, synchronous workers have incomplete shutdown ownership, and browser chat grows with live traffic. The daemon still mirrors durable propagation associations in heap strings and retains variable-sized events/replies without an aggregate byte budget. These mechanisms need attribution; none alone proves the current production growth cause.
**Expected Outcome:** Persisted history and admitted work remain correct while process/private memory reaches a stable plateau, UI caches and DOM remain bounded, slow peers cause observable backpressure, and workers stop without accumulating threads or descriptors.
**Target-Perspective Output:** An operator runs the committed Linux soak runner against isolated RCH and reticulumd services. Its machine-readable report links exact source/binary hashes, fixture cardinalities, verified deliveries, poll results, memory/swap time series, queue/cache budgets, maintenance and shutdown results. The operator can reproduce the test without production credentials or data.
**Truth Owner:** SQLite owns historical RCH messages, domain records, command results and propagation associations. RCH core owns northbound business validation and durable pre-admission intent; the SDK/daemon owns admitted LXMF delivery, route selection and retry. The UI owns presentation and a bounded view cache only. Runtime owners own their cancellation, admission and join handles.
**Contract Boundary:** Preserve northbound routes, payloads, ordering, authorization, replay, idempotency and delivery semantics. Preserve SDK wire correlation and detailed explicit inventory replies. Internal caches, duplicated strategies and snapshot command paths can be removed. A cache eviction must never initiate a new delivery.
**Cutover:** First establish measured baseline and resource diagnostics. Then replace durable read/write paths before enabling eviction, migrate each command family atomically, redirect all queue producers through one budget, and replace detached actors with explicit runtime ownership. Remove each displaced internal path when its last caller moves.
**Displaced Path:** Full-history runtime message hydration, resident-only durable transitions, delete/insert raw message identity, full attachment scans, broad command snapshots/deltas, unbudgeted envelope admission, detached actor registries, and unbounded chat accumulation/rendering.
**Value Density:** Prioritize measured daemon retention/churn and RCH historical allocation first. Use existing SQLite transactions, SDK clients, runtime cancellation and UI API clients; avoid a parallel scheduler or business engine.
**Acceptance Evidence:** Required issue-specific regressions and repository gates plus a final >=3-hour constrained real RCH/daemon run with large durable state, continuing valid messages/announces, dashboard/history requests, slow/unavailable reply phases and recovery. Measure anonymous/private memory plus swap, not RSS alone. The final workload and budgets are fixed before the final run; a failed run cannot be made passing by weakening them.
**Evidence Lane:** Local source regressions, local constrained real runtime, browser runtime, and hosted/public-release evidence are separate lanes. Readiness/HTTP 200 and a short smoke do not substitute for delivery or memory evidence. No production operation or release is implied.
**Kill Criteria:** Do not retain dual authoritative caches, silent lossy migration, detached unbounded blocking work, count-only admission for variable payloads, or an idle-only soak. Any lost durable record, duplicate accepted delivery, growing resource trend, fresh poll timeout after recovery, OOM, or misreported shutdown fails acceptance. If historical workload or real transport cannot be exercised, record implemented but unproven and keep the goal active.
**Architecture Slice:** RCH core SQLite stores/migrations and domain commands; server message persistence/receipts/retry/runtime workers; transport actor queues; shared Vue chat store/view/lifecycle; daemon propagation store, event ownership and ZeroMQ reply path; a committed Linux fixture/load/measurement runner.
**Plan Review Gate:** Requires PRE review before execution.

## Baseline and protected state

- Clean paired checkouts: RCH `96f71a639f041cec48beb553af9af15e2a49e7ce` and LXMF-rs `04a0ba5e5676a521c87bd7d77064bacf598f08e6`, under `/tmp/rch-resource-stability/`.
- Preserve the unrelated dirty canonical LXMF checkout and untracked canonical RCH `design-qa.md`.
- No production database, service, host setting or credential changes. Use isolated temporary databases, endpoints and user cgroups only.
- Existing preview.18 artifacts provide the baseline; rebuilding must record exact source/binary provenance and avoid shared-target freshness errors.
- The #657 production evidence spans about 13h40m. A three-hour local run is a minimum qualification, not a claim to reproduce all production/public-network conditions.

## Policy gates

User questions already pending:

1. Historical normalized message-ID collisions: latest row plus archived originals, earliest plus archive, or abort/report. Do not implement a collision resolution policy until answered. Payloads must be preserved whichever policy is selected.
2. Cache budgets: proposed recent 500 / 16 MiB / 24h, active 32 MiB, or a smaller/custom selection. Durable paging and point-transition work can proceed before this answer; final eviction/admission policy cannot.
3. Optional acceptance target: proposed three-hour production-shaped local run or a user-selected longer/live target. Proceed with the three-hour minimum if no steering arrives; final resource budget must be recorded before launching the final run and must not be tuned after a failure.

## Numerical limit ownership and freeze gate

| Limit | Owner / decision | Freeze gate |
| --- | --- | --- |
| Collision resolution and recent/active message retention | User policy questions above | Before migration/eviction implementation |
| UI per-conversation/global bytes, dedup age and pending allowance | Presentation engineering limit, preserving durable paging and pending semantics; derive from measured record sizes and document defaults | Before T11 implementation |
| RCH transport global/per-client/per-destination bytes | Admission engineering limit, tied to selected active budget and documented envelope/recipient estimates; explicit durable defer or rejection | Before T7 implementation |
| Daemon event/reply/in-flight bytes and oversize behavior | SDK contract engineering limit, measured current payload distribution and protocol size limits; document observable overload | Before T3 implementation |
| Plateau warmup/windows/slope, absolute process budget and allowed accounting overhead | Acceptance engineering criterion proposed to user; record raw memory+swap and private/anonymous accounting separately | Before final run, immutable in run manifest |
| Normal-load throughput/latency tolerance | Baseline-relative acceptance criterion with absolute successful-delivery and poll-error requirements | Before comparison/final run |

T1/T2 can gather measurements without selecting these limits. Explicitly record every chosen numerical value and rationale before its dependent task; a post-failure value change creates a new experiment rather than converting the failed run into success. Retention/business policy questions remain human-gated. A fixture must remain representative after warmup/maintenance; cardinality collapse is a failed workload, not a memory improvement.

## Architecture map and cutover details

### RCH durable message and domain boundaries

- Core `src/lib.rs`: `RchCore.messages`, `RchCoreSnapshot`, runtime hydration, migrations, queue projections and normalization. Export snapshots may remain full history; runtime bootstrap must use a separate bounded reader.
- Core `src/sqlite_commands.rs`: current broad command reservation and raw message upsert; `sqlite_record_updates.rs` already demonstrates keyed immediate transactions. Add cohesive store modules rather than enlarging the giant root file.
- Server `src/message_persistence.rs`: resident-only `current`, `transition`, and attempt validation must become durable atomic point operations. Commit before cache/event publication.
- Server `src/lib.rs` and extracted modules: receipt callbacks, retry selection, status polling, chat history/counts, join replay, REM scheduling and diagnostics all need durable reads before cache eviction.
- Active work includes pre-admission retries, current attempts, uncertain/partial admission and pending receipt reconciliation. Reuse existing semantic predicates, including failed rows with unresolved per-target admission. Do not infer activity from delivery-state strings alone.
- Indexed message identity must use existing normalization (trim/lowercase/UUID compact form), preserve payload and stable integer identity, and backfill with restart-safe bounded keysets.
- Attachment query projection is topic/category; no existing mission/scope authority exists to invent.
- Commands retain validation in core. A bounded affected-aggregate core may be used under the same immediate transaction; commit explicit changed/deleted keys only, never infer deletion from unloaded collections. Command-result lookup and insertion are keyed and atomic with domain/audit/event effects.
- `rch_outbound_jobs`/`rch_domain_events` schemas have no execution owner today. Reuse only with an explicit cutover, never create a second scheduler/event authority.

### Queue/lifecycle boundary

- Transport `src/lib.rs` data-plane and legacy actor producers: reserve estimated envelope/expansion bytes before enqueue, release with RAII on every completion/rejection/cancel/drop. One owner handles admission, cancellation, operation deadlines and joining.
- Server `runtime_delivery_workers.rs`, `runtime_exit` and runtime finish paths: stop admission first, cancel cooperative operations, wait boundedly and report incomplete shutdown. Arbitrary synchronous Rust threads cannot safely be killed; a fixed pool only bounds accumulation. Any genuinely non-cooperative dependency needs an owned helper process or tested process-exit fallback, with an external shutdown deadline test. Normal real SDK operations must have cooperative cancellation/deadlines and joined owners.
- Daemon event logs, broadcasts and response queues: account retained heap ownership/copies and active replies, including oversized single payloads. Correlation and reliable rejection behavior must stay intact.

### UI boundary

- `ui/src/stores/chat.ts` and chat view/components: per-scope recent window, global byte cap, bounded dedup/tombstones, pending outbound reconciliation, stale-response generation guard, paged older durable history and bounded virtual DOM. Existing API client remains the only network owner.
- `ReticulumConfigEditor.vue` polling: lifetime generation/cancellation, no timer started after unmount, no overlapping refresh; use the existing UI lifecycle conventions.
- Follow `FRONTEND_ENGINEERING_PRINCIPLES.md`; source/build unit tests alone do not prove browser heap or rendered-window behavior.

### Daemon propagation boundary

- `rns-rpc/src/rpc/daemon/init_parts/rpcdaemon_sections/default_ticket_expiry_secs.rs`, peer restore/query paths and storage propagation modules: SQLite is the association owner. Trace all `restored_*_ids` consumers before removing/replacing cache residency; preserve legacy import once and explicit query semantics.
- `rns-rpc/src/rpc/daemon/events.rs` and reticulumd `zmq_rpc_loop` modules: diagnostics distinguish handler queueing, handler execution and response delivery, byte/item occupancy, maintenance duration/backlog, and failures. Avoid full-payload logging.
- Remove million-string residency only after read consumers use durable keyed/paged views. Do not hide growth with periodic allocator trimming or restarts.

## Ordered task board

Each task is implemented by the main agent sequentially. Read-only review and independent verification may run concurrently only under the skill's required roles. No overlapping write scopes.

### T1 — Reproducible fixture, load runner and evidence format

**Allowed files:** RCH `scripts/resource-stability/`, `docs/goals/resource-stability/`; narrowly scoped LXMF test-support/probe modules or `lxmf-core/examples/propagation_resource_fixture.rs` and RCH `r3akt-rch-core/examples/resource_fixture.rs` for typed codec/signature serialization. Avoid application changes in this task.
**Output:** Valid typed SQLite fixtures (about 1,000,000 associations, 940 historical peers, 512 active peers, about 135k payload records totaling ~71 MiB; RCH 100k announces and >=25k terminal messages with attachment metadata and active work), real transport sender/receiver plus UI/API traffic, process/cgroup sampler, report and checksum manifest.
**Verification:** Runner `--self-test`; preflight verifies cgroup delegation and effective memory.high/max/swap/CPU affinity, /proc accounting and browser instrumentation, recording actual values (fail the constrained lane if unavailable). Generate historical payloads with existing LXMF codec/signature helpers, not arbitrary hex. Validate stored wire payloads through daemon operations, then verify fixture cardinalities after startup and one actual maintenance cycle; unexpected quarantine/pruning or inert associations fails fixture qualification. Verify seeded pending/completed transitions separately from newly delivered unique messages. Small end-to-end baseline phase and injected report failure must pass.
**Evidence:** Baseline time series and independently verified message IDs, not receive counters. Reserve isolated ports/socket paths and cleanly join children. No destructive production access.
**Depends on:** PRE approval. **Parallel safe:** Documentation/review reads only.

### T2 — Attribute daemon growth and add bounded-stage diagnostics

**Allowed files:** LXMF daemon/RPC propagation/event/ZeroMQ modules, focused tests, `docs/issue-657-investigation.md`; RCH harness only for integration measurement.
**Output:** Repeatable current-source retention/churn measurement; maintenance/queue/handler/response timing and occupancy. Distinguish live allocations from allocator-free retained pages where safely measurable. Document limits if allocator tooling unavailable.
**Verification:** Existing #657 probes, focused RPC/daemon tests, stage timeout/recovery tests; short cgroup baseline under traffic and maintenance.
**Evidence:** Identify measured dominant owners or allocation-producing stacks; do not infer current allocator composition from the old build's probe.
**Depends on:** T1. **Parallel safe:** Read-only review only.

### T3 — Remove measured daemon amplification and bound variable payload ownership

**Allowed files:** LXMF `rns-rpc` propagation/event/store modules, reticulumd ZeroMQ modules and their tests/contracts.
**Output:** Durable association reads replace redundant runtime inventory where measured; count+byte limits cover retained events/replies and in-flight work. Preserve explicit reply schema, ordering, import precedence and correlation. Propagate/log visible overload; never silently lose admitted work.
**Verification:** Pending/completed/restart/concurrent queue regressions, oversize event and slow-reader floods, drop/cancel budget release, all #657 probes, daemon issue369 scanner, boundaries/module-size checks and strict relevant lint/tests.
**Evidence:** Same workload comparison showing reduced live ownership/churn without lost/double delivery, bounded memory with a slow consumer and reliable RPC recovery.
**Depends on:** T2 measured attribution. **Parallel safe:** None for implementation.

### T4 — Indexed identity/attachment migration (#256)

**Allowed files:** RCH core SQLite schema/migration/message/attachment modules and focused tests; server adapters only to redirect callers.
**Output:** Restart-safe normalized message key and unique index, archived collision payloads under selected policy, atomic upsert preserving row identity; indexed topic attachment operations with consistent payload projection. No full-table decode for a one-topic update.
**Verification:** Populated upgrade/interruption/restart/collision fixtures; `EXPLAIN QUERY PLAN`; ordering, state and metadata preservation; DB/WAL byte comparison on repeated unchanged upserts.
**Evidence:** Same durable record IDs/payloads before and after migration, exact collision report, indexed plans and bounded batch allocation.
**Depends on:** User collision policy. **Parallel safe:** None.

### T5 — Durable message APIs before cache eviction (#252)

**Allowed files:** RCH core cohesive message query/transition modules; server `message_persistence.rs`, retry/receipt/chat/replay/read adapters and tests.
**Output:** Atomic durable point transitions and attempt checks; bounded eligible retry/reconciliation batches; durable chat pagination/counts/replay/history; runtime hydration excludes full historical message/audit/result arrays. Preserve endpoint-specific timestamp tie ordering and all filters.
**Verification:** Existing memory-reader/release-durability regressions plus late receipt after eviction, partial uncertain admission, retries after restart, replay, competing updates and commit-failure publication tests.
**Evidence:** Large durable history with fixed per-request allocation, complete paged history and no duplicate accepted delivery. Resident cache is not yet evicted until all consumers migrate.
**Depends on:** T4 for indexed key; independent SQL reader work can precede migration. **Parallel safe:** None.

### T6 — Bounded recent and active residency (#252)

**Allowed files:** Server extracted message cache/runtime bootstrap/diagnostics modules, core bounded bootstrap query and focused tests.
**Output:** Selected recent count/byte/age bounds, separate bounded active work backed by durable jobs/eligibility reads; eviction/hydration/count/bytes diagnostics. Oversized/active flood has explicit durable defer/reject policy, no silent eviction of necessary state.
**Verification:** Startup with large terminal history, high-volume inbound/outbound, age/count/byte bounds, active overload, nonresident late transitions and restart.
**Evidence:** Measured resident count/bytes match budgets and preserve every durable record; full message-history bootstrap path is no longer called.
**Depends on:** T5 and user cache policy. **Parallel safe:** None.

### T7 — Byte-budgeted RCH admission (#254)

**Allowed files:** Transport extracted budget/actor modules; server outbound durable admission/dispatch adapters and diagnostics; focused transport/load tests.
**Output:** One count+estimated-byte budget for retained envelopes, recipients and attachment metadata, RAII release, bounded next-eligible database reads, observable global and practical destination/client backpressure.
**Verification:** Max-payload concurrent producer flood; cancellation/full/disconnect/error release; slow delivery; normal ordering and throughput; no hidden alternate enqueue caller.
**Evidence:** Current/peak items/bytes/largest/oldest/reject/defer diagnostics and measured bounded overhead under load.
**Depends on:** T5 durable scheduling and T6 selected active policy. **Parallel safe:** None.

### T8 — Targeted command transaction primitive (#255)

**Allowed files:** Core new command transaction/read-set modules and tests, `sqlite_commands.rs` entrypoints, server `command_persistence.rs`; narrowly scoped root module wiring, permission endpoint adapters/SQLite diagnostics and their focused tests.
**Output:** Immediate transaction with keyed idempotent result/audit/event persistence, explicit changed/deleted rows and metrics; remove unchanged upserts. Existing domain validation reused; no unlocked read/then-write.
**Verification:** Rollback, competing state updates, duplicate command IDs and constant-allocation one-record mutation against large unrelated collections. Query-plan/rows-read/written/WAL evidence.
**Depends on:** None after PRE; can precede T4–T7 if policy responses pending. **Parallel safe:** None.

### T9a–T9i — Move all command families, one family per checkpoint (#255)

**Allowed files:** Core command read-set/write-set modules and focused tests, server corresponding command adapter. Do not change northbound routes or validation semantics.
**Families/read sets:** (a) marker/zone keyed rows; (b) skill/rights/moderation/log/change target and referenced auth/domain rows; (c) mission target/ancestry/linked dependencies; (d) team/member target and affected relationships; (e) EAM/assets/assignments affected links and generated changes; (f) checklist template/source columns; (g) checklist/task/cells and affected cascade rows; (h) southbound protocol roster/topic/subscriber/message commands; (i) REM registry mutations. Every family also loads the keyed capability/operation-right, client/topic/subscriber and team-routing dependencies used by common authorization and routing. Inventory command types and all call sites first, including inbound mission sync (`command_persistence::mutate` at server `lib.rs`), southbound handling and HTTP/checklist adapters; a list of HTTP routes alone is not the cutover audit.
**Output each:** Bounded affected aggregate, atomic validation/mutation/result/audit/event commit; no interpretation of unloaded rows as deleted. Domain-generated dependent changes preserved.
**Verification each:** Existing family compatibility tests plus competing/rejected commands, result reuse, generated events and bounded allocation/SQL row count with large unrelated history. Run required workspace and committed server readiness gate per completed family slice.
**Evidence each:** Single-row changes do not decode or rewrite unrelated families. Audit all original call sites and command types, including southbound and inbound mission sync. Last family deletes/demotes broad command snapshot/delta path; compatibility snapshots remain read-only.
**Depends on:** T8; implement a–i sequentially after the bounded direct-right checkpoint below. **Parallel safe:** None.

#### First bounded checkpoint: direct operation-right mutations

Implement this partial T8/T9b slice before T9a. The three direct permission
mutation adapters (identity capability grant/revoke and operation-right upsert)
currently use the broad command transaction without command IDs, audit records,
domain events or marker/zone changes. Their domain read set is one normalized
five-column operation-right key; no linked mission/member history is required.
This slice does not introduce durable command replay or change sync authorization.

**Allowed files:** Core `operation_rights.rs`, `sqlite_operation_rights.rs` and
focused tests; core root only to move the existing domain implementation and
wire exports; server `operation_right_persistence.rs`, root endpoint/read-helper
cutover and fixed SQLite metrics, focused permission/durability tests; these goal
documents. No message retention, collision, transport, UI or sync changes.
**Truth owner/cutover:** Reuse one core normalization/record-construction path.
Acquire `BEGIN IMMEDIATE`, read at most the matching row using the existing
composite primary key, preserve its grant UID, and UPSERT only a changed row.
Commit before returning its payload. Remove the production write branch of the
permission snapshot helper; keep broad commands only for unmigrated families.
**Contract:** Keep route authentication, kill-switch protection, normalization,
validation errors (400), database/decode/commit failures (500), capability and
operation-right response shapes. Do not synchronize the distinct legacy
identity-capability table or invent audit/result/event effects. Do not acquire
unrelated marker/zone cache locks.
**Evidence:** Stable UID across restart and competing connections; unchanged
requests write zero rows; validation/failing commit leaves durable state intact;
primary-key query plan; large malformed unrelated history is never decoded;
matching rows/changed rows/decoded payload bytes and elapsed time are reported
with explicit accounting scope. Bound the decoded record to at most one and
changed writes to at most one. Reject target key/payload disagreement as storage
corruption before writing. Exercise all three actual HTTP adapters against large
unrelated history, checking response shapes, changed/no-op metrics and unchanged
unrelated rows. Run focused core/server compatibility tests,
required workspace gates and the committed server readiness gate. This is a
partial checkpoint; T8, T9b and issue #255 remain open until their full contracts
and runtime allocation evidence pass.

### T10 — Cancellable, joinable runtime ownership (#257)

**Allowed files:** Transport actor/client ownership modules, server runtime exit/delivery worker/finish modules, SDK deadline integration if necessary and their tests.
**Output:** Stop admission, cancel connect/send/receive/response/retry waits, bound actual operation and shutdown deadlines, own all actor join handles, a cancellation contract for real dependencies and process isolation at any genuinely non-cooperative boundary, diagnostics for stalled/cancelled/stopped/unfinished workers. Drop is best-effort cleanup only.
**Verification:** Shutdown at every blocking stage; a never-returning mock runs through the actual service shutdown path in an isolated child process and must terminate within the recorded deadline. A bounded thread pool alone is insufficient: Tokio runtime destruction can wait forever on `spawn_blocking`. For production APIs without cooperative deadlines, use an owned child-process boundary with terminate/kill/wait and explicit failed-operation reporting; do not claim an arbitrary Rust thread can be cancelled. Test unavailable-worker backpressure, late-completion no overlap/duplicate delivery, repeated start/stop/reconfigure stable threads/FDs/memory.
**Evidence:** Wall-clock shutdown result and joined-worker counts; report failure instead of falsely claiming completion when a non-cooperative worker remains.
**Depends on:** T7 admission ownership; may inspect/prepare earlier. **Parallel safe:** None.

### T11 — Bounded browser chat and poller lifecycle (#253)

**Allowed files:** `ui/src/stores/chat.ts`, cohesive chat cache/virtualization composables, chat view/components, `ReticulumConfigEditor.vue`, focused UI tests and harness browser driver.
**Output:** Per-scope recent windows/global byte bound, bounded duplicate tombstones, durable older paging, pending/recent-delivery preservation, stale fetch guard and virtual DOM. Poll timers cannot start after unmount and refreshes cannot overlap.
**Verification:** UI lint/typecheck/test/build; generation/pagination/late delivery/high-volume tests; browser sustained WebSocket traffic with heap and DOM measurements, scroll/backfill verification and repeated navigation.
**Evidence:** Browser heap and rendered nodes plateau under continuing messages, history remains accessible, server allocation remains bounded while UI is open.
**Depends on:** T5 durable pagination and selected cache policy; poller race can be fixed independently. **Parallel safe:** None.

### T12 — Final constrained real integration, acceptance audit and review

**Allowed files:** Harness, goal evidence/report/docs; changes to application only when a measured regression requires returning to its owning task.
**Output:** Final >=3h run after all code changes, two CPU execution environment, daemon MemoryHigh=512MiB/MemoryMax=768MiB and comparable bounded swap; RCH MemoryHigh=768MiB/Max=1GiB. Separate process accounting, large valid fixture, maintenance every300s, continuous UI and real messages/announces, retries/reconciliation, slow-peer recovery and repeated clean restarts in a separate lifecycle phase.
**Final-run preflight:** Record immutable builds, exact workload rates/seed/cardinalities, warmup, selected fixed byte budgets and explicit plateau criterion before launch. Reject a continuing increasing memory+swap trend; never use readiness, zero traffic or allocator trimming as success.
**Verification:** All repository-required fmt/strict Clippy/workspace tests, relevant daemon feature/boundary/module-size/issue369 checks, UI gates and committed server readiness runner. Run POST plan, correctness, maintainability and verifier reviews per Krypton execution roles; resolve major findings.
**Evidence:** Published local report with raw time series, successful unique deliveries and durable updates, poll latency/error intervals, thread/FD counts, memory/swap slope/window analysis, queue/cache/maintenance metrics and restart outcome. State local limitations, including no public mesh or live-server acceptance. Audit every acceptance requirement in all seven issues; keep goal active if any required work/evidence remains.
**Depends on:** T1–T11. **Parallel safe:** Read-only independent review only.

## PRE review disposition

The 8 October PRE review found no blockers and three major/two minor corrections. The plan now names a process-level shutdown boundary/test, all protocol/common-context command callers, operationally valid payload and post-maintenance fixture validation, effective cgroup/browser preflight, and a numerical-limit ownership/freeze gate. Re-review these corrections before T1 execution.

PRE re-review: aligned, no remaining blocker/major before T1. Execution started with isolated Linux-control preflight and fail-closed report regression tests. T1 remains in progress; no application fix or sustained acceptance claimed.
