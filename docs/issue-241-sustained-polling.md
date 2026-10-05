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
revision `d37d39b23d90c5bd75e80dcecab8030d87107421`, based on version 0.13.0.
The northbound API and identity authorization contract are unchanged.

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

The exact stripped daemon artifact also passed preserved-state/hot-restart
qualification with two newly imported messages and normal shutdown. Its one
readiness interruption occurred during the intentional daemon restart; readiness
was healthy after recovery. The rebuilt artifact must repeat sustained qualification against this saved state
before publication; release-specific evidence will be packaged in
runtime-verification.json. These loopback runs
do not establish that the production topology or
preserved state triggering the readiness stall has been repaired. Sanitized
interface configuration, stalled-process RSS and cgroup memory.stat anon/file/sock
measurements remain useful production evidence. Do not close the full issue from
stream-retention or restart-recovery evidence alone.
