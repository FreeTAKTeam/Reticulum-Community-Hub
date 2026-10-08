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

#### Next T1 checkpoint: populated real-delivery attribution

Extend the existing delivery preflight with `--fixture-from`, without changing
application/SDK behavior. Clone the immutable large fixture into fresh node0
and RCH databases; node1 stays empty. Verify source manifest/database hashes and
reject source WAL sidecars with uncheckpointed data. Keep TCP interfaces and add
the baseline propagation configuration only to node0; activate 512 existing
fixture peer IDs through its current control API. Record effective policy,
source/clone hashes, before/after logical cardinalities and bounded diagnostics.
Use the existing baseline's separate 120-second peer-activation setup allowance,
record its actual latency and restore the normal 10-second RPC bound afterward.
This does not change the frozen observation or shutdown deadlines. Preserve any
failed setup/forced shutdown evidence; do not relabel that run as passing.
Start both TCP ends before populated activation and retry both real service
announces through the public SDK/RCH owners within the existing 30-second setup
discovery deadline. Require learned signed identities; submission acknowledgement
alone is insufficient. Retain bounded discovery attempts, including on failure.
The public SDK fixture explicitly activates its created identity and specifies
that identity on every announce, rejecting a mismatched identity/destination or
rejected announce. Do not rely on implicit session-active identity selection.
Check source database hashes both before cloning and after cleanup. Record source
timestamp ranges and reject a fixture whose pending/completed TTL expires during
the frozen lane, identifying it as stale workload rather than daemon regression.

Use 65–100 unique pairs at the existing five-second interval. Freeze the whole
observation deadline as `max(480, messages * 5 + 60)` seconds in the manifest.
Require successful real pairs before maintenance, an actual successful storage
maintenance completion logged by the owned daemon after observation begins,
and a new pair admitted after that completion was observed. All pairs require
authenticated durable receiver/sender/receipt proof and zero new RCH poll errors.
Cache terminal SDK status results. Reuse dashboard API requests every 30 seconds
and bounded daemon resource sampling; add no synthetic announce ingress.

After maintenance retain all 135,893 original propagation payload rows with
unchanged content/metadata, at least 900,000 original associations across at
least 940 original histories, and all 100,000 original completed marks. New rows
cannot mask historical loss. Record removed original pending/added associations
and reconcile removals with logged pruning. Preserve all 100,000 original RCH
announces and 25,000 messages, including indexed columns and duplicate detection.
Compare through indexed/streaming reads, never million-row `fetchall()`.

**Allowed files:** Existing T1 harness/docs; cohesive fixture-preservation and
maintenance-evidence helpers plus focused regressions. No application changes.
**Gates:** Wrong hashes/cardinalities, missing/changed original rows, lost completed
marks, new rows masking loss, stale/missing/failed maintenance, lack of post-cycle
delivery, deadline expiry and failed cleanup must fail closed. Independent PRE,
correctness/maintainer and verifier roles review this bounded harness slice.
**Remaining:** Historical fake peer IDs model bookkeeping. This lane does not
prove network fetch/ack or pending-to-completed transitions of the deterministic
seeded receiver's payloads. Keep that operational propagation qualification,
continuing browser/lifecycle/slow-peer evidence and final plateau acceptance open.
`passed_final_acceptance` remains false, regardless of this checkpoint's result.

#### T1 diagnostic follow-up: freeze a non-burst periodic announce cadence

Populated attempts 5/6 failed the unchanged 30-second discovery gate. Attempt 7
adds only existing receive-admission debug logging and proves the peer held
RCH's valid announce for approximately 300–360 seconds under ingress control;
attempt 6 separately proves successful sender interface dispatch. The harness
forces periodic daemon announces every second, including several destinations
on a propagation node. The artificial cadence sustaining the receiver's burst
state is the hypothesis the changed-cadence experiment must test. This is not evidence that RCH's explicit identity
correction solves daemon memory growth or a production delivery incident.

**Allowed files:** The T1 delivery harness, focused harness regression, these
documents; no SDK/daemon/RCH production changes. Freeze periodic daemon announce
interval at 10 seconds for both nodes and record it in every new run manifest.
This produces approximately 0.3 periodic announces/second from the propagation
node, before protocol duplicates or manual discovery. This is a test input,
not a claim of equivalence to 285 unique imports/15 minutes. Keep manual public-SDK/RCH discovery calls, protocol ingress
limits, the 30-second discovery deadline, 120-second activation allowance,
480-second observation deadline, 65 continuing pairs, all history/cardinality,
maintenance, authenticated delivery and shutdown gates unchanged.
**Evidence:** Keep attempts 1–7 as failed experiments. The changed cadence starts
a separately hashed experiment; its result cannot turn a prior run into a pass.
Assert the manifest interval and both daemon launch arguments use the same
frozen value, then repeat empty and populated real delivery. Capture the existing
send/ingress trace for the first populated run and independently verify the
result. Do not disable ingress control or extend a deadline to gain a pass.

#### Separate application checkpoint: registered announce identity binding

Populated delivery attempt 3 registered RCH's SDK-derived service destination
but the peer learned only the daemon default identity after 27 acknowledged
`/Control/Announce` requests. Initial registration already specifies an identity;
later announcements use implicit session selection. This is insufficient to
prove the missing packet's cause. Correct the explicit identity contract as a
separate application checkpoint, outside T1's harness-only allowance.

**Allowed files:** RCH transport `sdk_identity.rs`, narrow root wiring/session
state, existing identity/recovery tests and focused new identity-contract tests;
these goal documents. No daemon/SDK production, queue, timeout, memory policy,
network, packaging or release changes.
**Truth owner/cutover:** The public SDK imports/activates/announces the identity.
Keep its returned bundle with the registered configuration in one session-owned
record. Registered announces must explicitly select that returned identity;
check activation acceptance and announce acceptance/exact identity/destination
before publishing registration/update success. Session recovery rebuilds the
record through SDK import. Do not derive identities or destinations in RCH.
**Contract:** Preserve standalone unregistered announce behavior and its
`Option<String>` result shape. Surface rejected or mismatched acknowledgements
as transport errors through existing callers. Never interpret an accepted
announce as proof of peer learning or delivery. No implicit retry or reimport on
each registered announce.
**Evidence:** Actual SDK frames prove explicit registered identity and unchanged
metadata, with no extra import/activate on repeated announce. Rejected activation,
missing/wrong identity or destination and rejected announce fail before success.
Update/recovery tests use full typed acknowledgement metadata. Standalone and
unavailable/recovery tests preserve existing behavior. Required workspace and
server-readiness gates, then frozen empty/populated real delivery with exact
learned identities and durable records. A repeated populated discovery failure
remains failed evidence and requires transport attribution, not a longer setup
deadline or a claim that this correction fixed its root cause.

The newer #657 evidence additionally requires follow-up T2 correlation of actual
SDK method/session/request and bootstrap phases, domain/store lock waits and
handler/reply timing. Keep those diagnostics and connection/recovery changes in
their own reviewed checkpoints. Final T5/T10/T12 evidence must include retained
history recovery after event-window expiry/restart, durable import before cursor
advancement, and operational progress independent of readiness. Current tmpfs
clones do not qualify production file-cache reclaim; final constrained acceptance
must account for service-charged file cache separately from process-private memory.

### T2 — Attribute daemon growth and add bounded-stage diagnostics

**Allowed files:** LXMF daemon/RPC propagation/event/ZeroMQ modules, focused tests, `docs/issue-657-investigation.md`; RCH harness only for integration measurement.
**Output:** Repeatable current-source retention/churn measurement; maintenance/queue/handler/response timing and occupancy. Distinguish live allocations from allocator-free retained pages where safely measurable. Document limits if allocator tooling unavailable.
**Verification:** Existing #657 probes, focused RPC/daemon tests, stage timeout/recovery tests; short cgroup baseline under traffic and maintenance.
**Evidence:** Identify measured dominant owners or allocation-producing stacks; do not infer current allocator composition from the old build's probe.
**Depends on:** T1. **Parallel safe:** Read-only review only.

#### Separate diagnostic checkpoint: SDK failed-exchange correlation

The latest #657 evidence shows that requested RCH polling can fail while the
daemon's actual poll counter stays flat and negotiation/import counters rise.
A request number alone cannot identify the session, method or completed stage.
This checkpoint adds failure context at the SDK transport owner; it is partial
T2 attribution, not a recovery or memory fix.

**Allowed files:** LXMF SDK ZeroMQ transport and a small sibling diagnostic
helper, narrow module wiring, focused transport tests, investigation notes and
these goal documents. RCH product/dependency pins, daemon production code,
deadlines, retries, transport reset behavior and response-correlation policy
remain outside this checkpoint.
**Truth owner/contract:** One stack-owned context per actual SDK RPC records the
generated session/request ID, actual method, current stage, elapsed time,
whether send completed and the saturating number of unrelated replies ignored.
Failed calls carry this context in a single namespaced error detail object and
in the error message used by existing RCH adapters. Preserve the already-mapped
`SdkError` code/category/retryable/actionable/cause/details/extensions exactly;
the existing remote mapper's loss of raw `RpcError` metadata is a separate
contract gap, and `support.rs` remains unchanged. Insert `sdk_zmq_exchange` only
when that detail key is vacant, never overwriting an existing value; on collision
the local context is message-only, and the existing detail is not trusted as
local diagnostics. The suffix always carries local context. No new logs, event
ring entries, global registry, background tasks or successful-call records.
The new detail/suffix never includes parameters, authentication, endpoints,
response bodies or peer session IDs; it does not sanitize or expand existing
error text/details. `send_completed` means local ZeroMQ send returned success,
not daemon receipt or processing. Each local method/session diagnostic string is capped at 128 ASCII
characters, replacing non-identifier characters; the generated session is
already bounded. This is a diagnostic representation bound, not an admission
or business-retention policy.
**Cutover:** Replace the request-ID-only timeout helper with the same transport
context used for connection/lock/send/receive/decode failures. Mapped remote RPC errors
may gain local context but keep their mapped semantic fields/details. The
PUSH/PULL path continues ignoring unrelated replies; DEALER continues failing
on correlation mismatch. A lock-wait timeout must not reset another owner.
**Evidence:** Both endpoint modes, cold connection and lock-wait failures;
actual negotiation/import/poll method distinction; completed send followed by
timeout and ignored replies; malformed reply, DEALER mismatch and remote error
metadata preservation including namespace collisions; bounded/redacted context and unchanged successful
recovery. Existing SDK transport suites, strict SDK lint and issue-369 scanner
where applicable. Independent PRE, correctness/maintainer and POST review.
No live acceptance claim until the owning application uses the exact source.

**Separate validation-only allowance:** Strict SDK all-target lint found three
pre-existing `uninlined_format_args` warnings: two test assertions in
`src/lifecycle.rs` and one gap warning in `examples/rpc_desktop_send.rs`.
PRE approved exactly those positional-to-captured formatting substitutions,
with unchanged text/format/behavior and no adjacent refactor. Keep this cleanup
separate from the diagnostic implementation and verify the exact diff.

#### Separate application checkpoint: exact SDK receipt IDs

**Intent/evidence:** Populated attempt 8 delivered all 65 outgoing payloads in
both daemon stores, while RCH retained 38 as sent at the original 480-second
deadline. All 65 persisted RCH target IDs exactly equal the admitted SDK IDs;
no guessed `sdk-` aliases exist in the daemon. RCH currently probes that guessed
alias first. The SDK is the status/ID truth owner and uses an exact durable ID
lookup. Correct this extra application interpretation before a separate
cross-message scheduling change.

**Allowed files:** Server root only for `zmq_delivery_status`, the cfg(test)
legacy adapter, deletion of `reticulumd_status_message_id_candidates`, three
existing exact-request assertions and cohesive test-module wiring; new
`src/tests/sdk_receipt_polling.rs`; server dev-dependencies and their lockfile
entry only to reuse the already locked ZeroMQ socket and official RPC codec
crates; these goal documents. No production SDK,
daemon, transport, schema, retention or retry policy changes.
**Contract/cutover:** Treat the stored SDK message ID as opaque. Both status
adapters make exactly one lookup of that ID, with one budget decrement; a real
`sdk-` prefix is preserved. Remove prefix enumeration entirely. Preserve the
four-call budget, ten-second pass interval, five-second per-message cooldown,
newest-first outer ordering for this isolated comparison, target rotation,
eligibility, error-stop behavior, terminal snapshots, partial aggregation,
retry behavior and durable-before-publication semantics. No aliases, ID
migration, deadline extension, extra delivery strategy or re-admission.
**Evidence:** Actual ZeroMQ request capture for a non-prefixed SDK ID distinct
from the parent RCH ID, an already-prefixed opaque ID, not-found with no alias
retry, typed terminal durable update, transport/SDK error with pending state and
visible diagnostics, and more than four pending targets obeying the unchanged
four-call limit. Retain existing terminal-skip/restart, target ordering and
partial-admission regressions. Run focused tests, required workspace/server
readiness gates, freeze exact binaries/source/harness hashes, and repeat empty
and populated real delivery with unchanged deadlines and history/maintenance
gates. Independent PRE, correctness, maintainer, verifier and POST review.
**Limits/kill criteria:** This is a receipt-binding correction, not a memory
fix or final resource acceptance. Preserve attempt 8 as failed. Newest-first
cross-message fairness remains open; a failure after exact binding requires a
separately named scheduling checkpoint rather than larger budgets/deadlines.

#### Separate T2 experiment: local daemon heap attribution

After exact-ID receipt qualification, run a separately labelled instrumented
copy of the same populated real-delivery lane. The failed unprofiled attempt 8
increased node0 private+swap from 13.67 to 21.29 MiB and RCH from 156.13 to
169.30 MiB in 480 seconds; this is short failed-run evidence, not a plateau or
proof of a retained allocation leak.

**Allowed artifacts:** These goal documents and an evidence-only Python runner
using the existing harness. No application source, host package installation,
production configuration, memory/CPU controls, fixtures, workload rates or
deadlines change. The separately recorded diagnostic file-size limit below is
the only additional service control. Use the already downloaded, hash-recorded Ubuntu heaptrack 1.5.0
preload/interpreter/print artifacts from the ignored workspace target directory.
**Ownership/controls:** Inject `LD_PRELOAD` and `DUMP_HEAPTRACK_OUTPUT` into node0
only, copying its environment. Run the actual frozen daemon as systemd MainPID,
not a profiler shell wrapper. Preserve the harness's cgroup/CPU/identity/OOM and
owned cleanup checks. Write raw output to a fresh ignored directory on regular
workspace storage, not the limited temporary filesystem. Record preload/tool,
runner, application and harness hashes plus the actual per-service environment;
retain the unprofiled experiment separately. Set node0's systemd `LimitFSIZE`
to exactly 2 GiB before exec and verify both systemd's value and `/proc/limits`;
this is a diagnostic artifact bound, not a product retention rule. The wrapper
may intercept only its own node0 `systemd-run` argument vector to add this one
property and must record it separately from the unchanged memory/CPU controls.
Require at least 20 GiB free on the raw-output filesystem before launch and
check the reserve at observation checkpoints; fail and clean up owned services
on reserve/size failure, retaining partial files. No truncate/delete workaround. Never change perf security settings
or connect to a production server.
**Evidence:** One actual maintenance cycle and continuing authenticated traffic
with the unchanged fixture/history/receipt gates; verify raw profiler output
exists, then interpret offline and report dominant live/peak allocation owners,
allocation churn and unresolved symbols. Export `--print-massif` time-resolved
outstanding allocation bytes and align its relative clock with recorded startup
monotonic brackets, observation samples, maintenance and pre-stop time. Separate
global peak, live bytes before shutdown, total allocation counts/churn and exit
leftovers. Use `--merge-backtraces=0` for quantitative peak reports; merged
reports, if present, are non-additive rankings only. Every offline tool runs in
an owned process group with a 120-second wall-clock deadline, 4 GiB address-space
limit and 4 GiB output-file limit; terminate/kill/wait only that owned group on
timeout and verify it is absent. Record tool exit/status/hashes and preserve
partial output on any failure. Require the same free-disk reserve before each
analysis stage. No host-wide cleanup or workload/deadline relaxation. Compare process-private/anonymous/RSS
and swap separately from cgroup file cache and profiler overhead. The raw trace
and stack reports do not contain a payload dump. Exit-time reported leaks are
not automatically production lifetime leaks. If profiling changes behavior,
preserve the failed diagnostic result; do not relax the workload to claim a pass.
**Acceptance/limits:** This is diagnostic attribution only. It cannot satisfy
final resource acceptance or quantify an uninstrumented plateau. Do not infer
allocation ownership from RSS alone. Required independent PRE and artifact/
cleanup verification; no production ownership fix without its own checkpoint.

#### Measured T2/T3 checkpoint: project propagation response metadata

The independently qualified profile-1 populated run preserves all 130 real
message/receipt chains, history and maintenance with zero poll errors. Its
unmerged allocation report attributes 1,380,352 `String::clone` allocations to
`current_propagation_state -> response_meta -> handle_sdk_poll_events_v2`:
512 static peer strings cloned for each of 2,696 metadata-bearing poll calls.
These transient allocations have zero consumption at the global heap peak;
this is measured churn, not proof of a retained-memory leak or production cause.

**Allowed files:** LXMF `rns-rpc/src/rpc/daemon/sdk_auth_http.rs` only for
`response_meta`; a cohesive new focused response-metadata test include and
its existing test-root wiring; investigation notes and these goal documents.
No transport, dependency, schema, retention, event/reply admission, timeout,
retry, fixture or workload changes.
**Truth owner/cutover:** Keep `PropagationState` under its existing mutex as
the policy owner. Build only the existing `propagation_node` JSON projection
while that guard is held, then release it before reading contract version or
constructing other metadata. Remove the full-state clone from this hot path;
keep the explicit full-state public reader for callers that need its arrays.
Do not introduce a second policy snapshot/cache or nested lock order.
**Contract:** Preserve every metadata field, scalar/nullable value, stamp and
peering defaults, `control_allowed` ordering/content and existing poisoned-lock
behavior. The required `control_allowed` output allocation remains; unrelated
static/allowed/denied/prioritized peer lists and store paths are not projected.
**Evidence:** Actual SDK poll and other metadata-bearing RPC responses under
default/custom policy, including a large unrelated peer policy and nonempty
`control_allowed`, match the existing schema/values. Existing RPC tests,
strict affected lint/format/boundary/module-size/issue-369 checks; freeze a new
daemon and repeat the same real populated lane/profile controls in a fresh
directory. Verify full history/receipt/maintenance gates and disappearance of
the specific full-state-clone allocation stack. Preserve profile-1 and failed
analysis output; no deadline or memory-budget relaxation. Required PRE,
correctness, maintainer, independent verifier and POST review. No plateau claim.

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


### Authorized finish integration: immutable framework pin

After publishing the reviewed framework fixes, align the existing RCH Cargo
Git sources, lockfile, verification/release workflow `LXMF_REF` values and
current packaging/readiness/transition documentation to that one published
commit. Preserve dependency versions, features, unrelated lock resolution and
historical evidence pins. This removes the old SDK/daemon reference from the
current build path; it creates no new runtime owner or compatibility path.
Validate the exact Git source with locked Cargo resolution and the committed
server-readiness runner before publication. Keep the original frozen binaries
for the metadata-only counterfactual; that comparison must not change RCH or
the SDK fixture simultaneously. No release or production deployment is included.
