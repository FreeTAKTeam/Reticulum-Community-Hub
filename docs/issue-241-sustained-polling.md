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
Current RCH SDK dependencies and daemon-build references align to immutable
revision `bbde8f2ce35eef8e5a4d99042faed38c6b8fbf68`, based on version 0.13.0.
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
