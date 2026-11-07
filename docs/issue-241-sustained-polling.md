# Sustained SDK event polling: RCH issue #241

[Issue #241](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/issues/241)
reports inbound starvation, daemon readiness/announce timeouts, and cgroup memory
growth after deploying the issue #238 repair. Three separate stream defects were
reproduced. The production readiness stall has not been reproduced or established
as fixed; cgroup memory must not be treated as process RSS.

## Retained-window starvation

RCH inherited the SDK desktop Reject overflow policy. The daemon retains polled
events, so consuming them does not free its 1,024-entry log. Once full, Reject
permanently drops new events while polls continue successfully at cursor 1024.
An unchanged three-peer run and a two-worker run reproduced that freeze.

RCH now requests DropOldest in its shared SDK start request, covering initial
negotiation and actor recovery. Expired-cursor and StreamGap recovery remain under
the existing RCH owner. Negotiation changes the daemon's shared runtime policy;
another client's later negotiation can replace it. Other SDK defaults are intact.
The real RpcDaemon/ZeroMQ regression interleaves twenty batches of 64 events and
requires all 1,280 markers in order with continuing cursor advancement.

## Restoring an obsolete policy from saved domain state

The first exact paired candidate froze again at cursor 1024 despite successful
DropOldest negotiation and healthy readiness. Identity operations restored an
older persisted Reject runtime configuration: negotiation had changed memory
without saving the domain snapshot. Configuration patches likewise applied their
new policy/revision before restoring the older snapshot.

Both paths now restore under the existing domain-state lock before mutation and
hold it through persistence. Individual config/revision guards are released before
snapshot building re-locks them. Persistence failures propagate before success.
Regressions verify actual bounded-window retention in both policy directions and
saved configuration/revision; both failed before the correction. All 758 RPC
tests pass. This preserves explicit later policy choices by other clients.

## Preserved cursor after daemon restart

The event sequence resets in a new daemon instance while the cursor runtime scope
uses the same persistent identity. A saved cursor can therefore be ahead of the
new sequence. Previously, successful empty polls returned the stale cursor
unchanged. With cursor 1024 preserved, 888 polls imported zero events even though
peer messages received delivery receipts.

The daemon now returns the existing SDK_RUNTIME_INVALID_CURSOR error when a
cursor exceeds its assigned sequence counter. RCH already recognizes that error,
clears its persisted cursor and resumes polling. The check uses the monotonic
counter rather than the retained tail, because concurrent insertion may reorder
entries. Its lock guard is released before the event-log lock. Tests cover empty
and populated same-identity restarts, explicit reset, valid idle polling,
reordered retention and filtered lifecycle traces. This restores continued
imports; it does not promise replay of all events lost across a restart.

The correction is reviewed in
[LXMF-rs PR #654](https://github.com/FreeTAKTeam/LXMF-rs/pull/654).
The SDK dependencies and daemon-build references in that repair aligned to
immutable revision `bbde8f2ce35eef8e5a4d99042faed38c6b8fbf68`, based on version 0.13.0.
The northbound API and identity authorization contract are unchanged.

## Network worker starvation during storage contention

A controlled test of the published d37d39b2 daemon reproduced eight readiness
timeouts during a three-second SQLite write lock while a real TCP peer announced
and propagation maintenance ran every second. Both network workers waited on
synchronous storage operations; readiness and persistence recovered after the
lock was released. This establishes a contention defect, rather than the original
production trigger or its memory-growth cause.

The daemon now releases the destination guard before persistence and awaits the
existing ordered announce/identity writes on a blocking worker. Due propagation
maintenance is likewise awaited on a blocking worker, with the next interval
scheduled after completion. Storage ownership, ordering, authorization and error
reporting remain intact. A real-binary regression fails before the correction and
passes after it, requiring readiness and correlated ZeroMQ polling under a native
watchdog's database lock, then announce/identity persistence recovery and normal
owned-process shutdown. Identity announce can still legitimately wait for its
database commit while another writer holds the database.

## Evidence and remaining limit

- The RCH retention regression failed at cursor 1024 before the change and passed
  after it. The daemon same-identity restart regression failed before the cursor
  validation and passed after it.
- A three-peer, two-worker RCH retention run completed 30 minutes with 7,655
  events and zero polling errors. Real peer messages were received, exposed by
  /Chat/Messages and persisted, including after 15 minutes. Authenticated announce
  succeeded after that window. All owned processes stopped with exit code zero.
- The corrected daemon recovered imports using the preserved database/identity
  and recovered again after a hot daemon restart without restarting RCH. Two
  fresh real messages were imported, two cursor resets were recorded and the
  final error was absent. Shutdown stopped all owned processes normally.
- RPC and SDK suites, strict affected-package lint, daemon diagnostics regression,
  formatting, module-size and dependency-boundary checks passed. RCH's committed
  server-only release gate passed on CI-pinned Rust 1.88 both before and after
  the paired pin update.

The earlier cursor-only stripped artifact from revision `75b245bf` passed
preserved-state/hot-restart qualification with two newly imported messages and
normal shutdown. Its one
readiness interruption occurred during the intentional daemon restart; readiness
was healthy after recovery. The final stripped artifact from revision `d37d39b2`, paired with the aligned RCH
source, completed 30 minutes against the preserved state: 9,034 events, 11,358
polls and four distinct Delivered peer messages imported and persisted after run
start. It reset its cursor at startup and again after a daemon-only restart while
RCH remained running. The one sampled readiness interruption was the deliberate
restart; readiness recovered, late authenticated announces succeeded, and every
owned process exited normally. Both repositories' source checks passed, including
daemon HIL and independent interoperability. Consult runtime-verification.json
in the testing artifact for release-specific source, checksums and measurements. These loopback runs
do not establish that the production topology or
preserved state triggering the readiness stall has been repaired. Sanitized
interface configuration, stalled-process RSS and cgroup memory.stat anon/file/sock
measurements remain useful production evidence. Do not close the full issue from
stream-retention or restart-recovery evidence alone.

A separate allocation probe used the unchanged `7359ab22` daemon binary from
`reticulumd-test-0.13.0-rch238.2` in an owned systemd user service, with two CPU
affinity slots, two Tokio workers, MemoryHigh 512 MiB, MemoryMax 768 MiB,
TasksMax 512 and LimitNOFILE 65536. A separately accounted client completed
10,000 correlated ZeroMQ requests in 521 seconds. All 52 readiness samples
returned 200; daemon cgroup memory peaked at 6,320,128 bytes and process RSS at
21,872 KiB. Neither service recorded memory-pressure, high/max-limit or OOM
events, and both stopped normally. This did not reproduce the reported memory
growth through repeated response connections. It exercised a disposable database
and a raw client without RCH or mesh peers, so it does not qualify the production
topology, preserved state or its longer stall window.

The exact bbde8f2c stripped daemon and aligned RCH executable subsequently completed
30 minutes against preserved state: 9,038 events, 11,355 polls, four distinct
Delivered/imported/persisted messages, startup and hot-restart cursor recovery,
late authenticated announces and normal shutdown of all current/retired processes.
The only sampled readiness interruption was the deliberate daemon restart. Its
separate three-second contention probe returned all 158 readiness responses and
20 correlated polls successfully (maximum poll 54 ms), with persistence recovery.
Both repositories' source checks passed, including daemon HIL and interoperability.
The [daemon-only testing prerelease rch241.2](https://github.com/FreeTAKTeam/LXMF-rs/releases/tag/reticulumd-test-0.13.0-rch241.2)
contains only the executable, license, instructions and verification metadata.
Anonymous public download, checksum, exact archive contents, source tag and
executable help were independently verified. The paired soak records process RSS
without separate systemd memory limits; it does not establish the production
trigger or memory-growth cause. Existing rch241.1 assets and stable v0.13.0 remain
unchanged.

## Durable worker initialization recovery

The current durable-broker worker had a separate recovery gap: its one-time
storage setup returned permanently on any database-open failure. The RCH process
could remain active after the failure while intake, application, dispatch and
announce reconciliation never started. Restoring storage did not restart those
owners. This is a reproduced startup failure, not an established cause of the
original production stall after fifteen minutes.

Worker initialization now retries recoverable setup failures with the existing
500 ms to 30 second backoff. Setup failures remain visible in inbound error
counters and the durable broker intake lane; successful initialization clears
the lane error, and successful polling clears the current inbound error. Static
missing configuration still fails immediately. Terminal exit wakes retry waits,
awaits any active blocking opener, and joins the worker. Purge prevents reopening
the database. All store-slot guards are acquired and checked before any store is
opened or published, so a failed attempt cannot strand partial ownership or
replace an existing owner's connections.

Controlled RpcDaemon/ZeroMQ regressions exercise unavailable storage followed by
restoration and message import without restarting RCH, exit during retry, and
all-or-nothing connection publication. The storage-restoration regression fails
on the previous implementation because the worker has already exited. An
additional initialized-worker regression holds a native SQLite writer until
intake reports a busy-store error, requires a registered identity announce during
contention, then releases the writer and requires both queued inputs to be
imported. These checks establish bounded recovery in the tested paths; they do
not reproduce or explain the original deployment's topology or memory growth.

The current paired source baseline is LXMF-rs version `0.16.1` at immutable
revision `b694d9f765c1783f255602967a625488c8804f4c`. RCH dependency locks, matching
daemon workflow checkouts and runtime metadata use that revision. This is a
source-built baseline; `release_tag` is null because no published release tag is
asserted to identify this source. It includes the subsequent propagation budget
and delivered-proof repairs alongside the existing event-stream fixes.
It also contains snapshot allocation/codec and owned-interface shutdown
corrections from the subsequent persistence investigation. The allocation increment
reserves an exactly sized MessagePack output buffer. A controlled debug probe
with 100,000 routes reduced peak extra requested allocation from 54,477,376 to
43,011,557 bytes (21.0%), with unchanged output bytes. These allocation counters
exclude resident-memory and cgroup effects; release runtime qualification remains
required. Requalification of this newer source remains pending; the native
result below identifies its earlier exact runtime and does not qualify this pin.

## Independent native continuity qualification

The frozen RCH debug binary from
`3665b92df7b5a94fef9b2d754e1c61a2c78780be`, paired with the SDK at
`10a19fb9174e420789d37f359c20ee317b0141f8`, passed a 1,228-second native run.
Its SHA256 was
`6ad83d0a0fe5bc4a3a05f28b5920c2dca2415870d874591a2e2e9a51ad10f1d2`.
The release daemon's production source was
`6858828f584f4043b1f99fef38ae55baea83ee59`; its unchanged binary was independently
matched by SHA256. Source, binary and harness hashes were checked again after
the run.

Two isolated daemons exchanged real TCP traffic through RCH and the public SDK:
41 unique messages in each direction, with all 82 full payloads verified against
authenticated, encrypted receiver rows and actual delivered sender receipts.
RCH outbound verification also required matching terminal durable dispatch
admissions. There were 11,257 polls with zero errors and 40 successful announce
calls; a peer's observed RCH announce timestamp advanced by 1,164 seconds. The
same broker journal finished with stored/applied checkpoints of 123/123, no
pending inbox or dispatch work, and no lane errors. Maximum sampled readiness
latency was 23.85 ms. After a two-second remote-daemon execution pause and
resumption, fresh messages completed delivery. This induced neither a restart
nor a disconnect. Every owned service exited with code zero without forced
cleanup.

This run used empty histories, native processes and CPU affinity, with no
per-service memory budgets. It does not establish a constrained memory plateau,
recovery against retained production state, or Columba/Pixel and Ratspeak/Windows
physical-client compatibility. Heavy retained-state and hours-long acceptance
remain pending. The original production stall and memory-growth trigger remain
unproven.

## Follow-up qualification status

A later constrained retained-state preflight of the preceding pair recorded a
one-event increase in `memory.events.high` during observation, so it did not pass
resource acceptance. Its release-profile RCH recovery stage verified initial
bidirectional delivery and restart recovery, then stopped before Topic message
admission when a newly created SDK identity was not discovered within 30 seconds.

An isolated frozen-binary probe reproduced the discovery symptom and traced it
to the intended fresh-interface ingress guard holding burst announces for about
360 seconds.
With only three seconds of spacing before each identity creation, both identities
were learned on the first attempt under the same protection and 30-second
deadline. Qualification setup must discover persistent recipients before enabling
sustained one-second announce load. These failed lanes and the paced discovery
control do not qualify the new source pin or hours-long resource acceptance.

A later release pair using LXMF-rs `c37f4c88` completed a 20-minute retained-state
correctness window with 41 bidirectional message pairs and four Topic fanouts,
plus an RCH restart after a committed acknowledgement was lost and fresh
delivery afterward. It still failed the strict local resource gate: four
`memory.events.high` events were added across four persistence checkpoints. The
subsequent primary-daemon restart stopped at a guard requiring at least 100,000
active paths, with 99,998 active paths observed.

Offline identity comparison found exactly 100,000 distinct retained destinations
across active and tunnel state: 99,997 seeded routes and all three real peer
identities. The missing seeds were precisely the first three keys evicted by the
declared 100,000-entry announce cache when new destinations arrived. All retained
seeded route packet hashes, interfaces, next hops and hop counts matched the
fixture. Both SDK recipients retained valid signed cache packets and tunnel
entries. The exact bootstrap interface-skip counts were not captured; asynchronous
TCP acceptance can race the restore mapping. This exposes a count-only fixture
guard assumption and does not convert the failed lane into a pass. The new pin
still needs exact identity recovery evidence and hours-long resource acceptance,
without forced announcements manufacturing missing retained routes.

The following release pair using LXMF-rs `74c019c3` passed its retained identity
proof, but fresh SDK-to-RCH delivery after the primary restart was marked
`source_identity_unknown`. Periodic destination cleanup had removed a source key
restored from a valid detached tunnel because its dynamic active interface was
unmapped. The final pin retains identity references from live tunnel paths until
the last tunnel reference expires. Its deterministic regression also verifies
release after expiry and preserves invalid-cache rejection controls.

An independent local TCP comparison used the same driver and unchanged 60-second
authentication gate, with empty histories, a detached saved route and a retained
tunnel. The frozen `74c019c3` release failed source authentication after cleanup;
the corrected debug daemon passed fresh authenticated, encrypted delivery in both
directions in 5.352 seconds. It used no scoped SDK reannouncement, route deletion
or cache rewrite, and all owned processes exited with code zero. This establishes
the focused recovery behavior, not release memory acceptance. The `74c019c3`
20-minute regular resource lane remains failed, with checkpoint high-event deltas
of +6/0/0/0. A fresh constrained release preflight and the four-hour lanes remain
pending; the final source has no hours-long acceptance result.

The final daemon-only increment repairs a replay-hash shutdown cutoff. The early
route checkpoint must precede interface retirement, but native ingress can still
remember packet hashes while that checkpoint is written. The daemon now saves
only the replay hash list after native interfaces and receipts drain, preserving
the earlier route snapshot and the closed background-save fence. A deterministic
late-packet regression fails before this fix and passes afterward; focused daemon
replay/restart checks pass with and without ZeroMQ. This is lifecycle correctness
evidence, not application authentication, custody or resource acceptance.

The change from LXMF-rs `ba8fc235` to the current pin affects only daemon shutdown
code, its lifecycle regression and evidence documentation. Shared libraries, SDK
and RCH runtime code are unchanged. Earlier paired binary and runtime results
remain attributed to their recorded revisions; the final release pair still
requires a fresh constrained preflight and hours-long qualification.
