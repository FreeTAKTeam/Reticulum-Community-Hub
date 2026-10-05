# Issue 241 sustained inbound runtime repair

**Intent:** Repair RCH issue #241, changing the daemon only when evidence requires it, and publish the validated testing release.
**Current Behavior:** PR #240 at 4f9980b uses the SDK desktop default Reject overflow policy. The daemon retains polled events; its 1024-entry log fills and rejects subsequent events. A three-peer unchanged run reached cursor 1024 and stopped importing announces while polls still succeeded. Production also reports readiness/RPC stalls and cgroup memory growth after about 15 minutes; that portion remains unproven locally.
**Expected Outcome:** Announcements and messages continue beyond event-window capacity; readiness, polling and authenticated announce remain responsive through sustained use and restart with preserved state.
**Target-Perspective Output:** An operator can continue announcing and receiving real mesh traffic after the reported failure window, using published artifacts whose source and checksum are verified.
**Truth Owner:** LXMF-rs owns the bounded retained event log and transport; RCH owns its stream-consumer negotiation, cursor persistence and inbound import.
**Contract Boundary:** Existing SDK v2.6 ZeroMQ negotiation and correlated event batches; RCH northbound routes and identity authorization remain intact.
**Cutover:** RCH explicitly negotiates DropOldest for the continuous event consumer. Keep the existing expired-cursor/StreamGap recovery. Do not change the SDK default for other clients.
**Policy scope:** Negotiation updates the daemon's shared runtime overflow policy; it is not session-local. Another client's later negotiation can replace it. Keep the daemon as the policy owner.
**Displaced Path:** RCH's inherited Reject event-retention policy, which permanently rejects new events after the retained window fills.
**Value Density:** One consumer-owned policy change prevents permanent inbound starvation. Additional edits require their own failing evidence.
**Acceptance Evidence:** A real RpcDaemon regression that consumes more than 1024 distinct events using RCH's actual negotiation; 30-minute RCH/three-peer qualification with polling, readiness, memory/descriptors, authenticated announce, actual message persistence, daemon restart and cursor recovery; applicable repository checks; hosted checks; exact published artifact verification.
**Evidence Lane:** Deterministic regression plus owned loopback peers and preserved temporary state. Production topology, memory.stat and stalled-process evidence are requested. Do not claim the entire production stall is fixed from retention evidence alone.
**Kill Criteria:** No duplicate polling or transport path, weakened timeout/security/retention tests, speculative socket pools, unrelated refactors, or source changes in the dirty sibling checkout.
**Architecture Slice:** RCH crates/r3akt-transport-rns/src/lib.rs (start negotiation); focused regression module in the same crate; runtime qualification support and evidence. Daemon checkout /tmp/lxmf-rch-241 is reserved for a separately evidenced daemon correction. Preserve design-qa.md and /home/pgiuseppe/Documents/LXMF-rs changes.
**Plan Review Gate:** PRE review required before implementation. The user goal authorizes the repair and publication; the PRE gate checks the plan, not a new permission requirement.

## Tasks

1. Reproduce and retain authoritative baseline evidence. Main owns temporary runtime harnesses. Record stream freeze separately from readiness/memory symptoms; never present hypotheses as root causes.
2. PRE review the confirmed RCH retention slice. Reviewer checks owner, protocol behavior, cursor-gap recovery and proof scope. Fix blockers before implementation.
3. Add a failing regression using the real RpcDaemon, RCH's actual SDK negotiation, and more than 1024 distinct events consumed in bounded batches. Main owns implementation in the transport crate. Then explicitly set DropOldest in RCH's start request and show the regression passes. No parallel source edits.
4. Continue sustained stall diagnosis. Run with production-like two Tokio workers and real peers; inspect resource state and thread/lock evidence if stalled. Only implement a daemon change after a concrete failing regression identifies the defect; update this plan and review that slice first. No fallback to a merely easier passing scenario.
5. Qualify the repaired pair beyond the reported failure window, including real inbound message persistence and announce near the end, restart/cursor recovery, and clean shutdown. Save compact evidence without identities or databases.
6. Run required Rust formatting, strict workspace clippy and workspace tests, focused backend suites, release build and applicable release-readiness gate. Inspect current PR checks before committing/pushing and wait for terminal hosted results. Report any baseline/platform gate separately.
7. POST review correctness, maintainability and target-perspective evidence. Integrate the fix into the existing repair branch/PR, and publish the requested daemon-only testing artifact if a daemon correction is necessary. Reconcile RCH release scope with the user's latest daemon-only instruction before publishing extra artifacts. Verify public downloads, source revision, contents and checksums independently.

## Current board

- Retained-window starvation: reproduced and corrected under RCH's shared start negotiation; the real-daemon regression receives all 1,280 ordered markers. Other clients still control their explicit shared-policy choices.
- Preserved cursor after restart: reproduced and corrected by the daemon's existing poll owner; RCH's existing reset path resumes imports.
- Saved-policy restoration: reproduced and corrected under the existing domain snapshot owner; negotiation/configuration persistence regressions pass.
- Storage contention: actual two-worker daemon starvation reproduced with a real TCP peer and a native external SQLite writer. Awaited blocking boundaries preserve ordered writes and non-overlapping maintenance. PRE and POST reviews pass; the durable regression fails before and passes after the change.
- Production-specific trigger and memory growth: unproven. The isolated cgroup probe did not reproduce the reported growth. Separate service memory breakdown and sanitized production interface/state evidence remain missing.
- Local gates: affected daemon tests, strict all-feature lint, diagnostics scanner, formatting, module size and boundaries pass. Aligned RCH Rust 1.88 server release-readiness passes, including strict workspace clippy, serial workspace tests, rustdoc, document links, optimized build and HTTP smoke.
- Exact artifact: rch241.1 is published and independently verified. The new bbde8f2c stripped rch241.2 candidate passes forced storage contention (158 healthy readiness samples and 20 successful correlated polls); its separate 30-minute RCH/three-peer qualification is running with preserved state and distinct fresh-message markers.
- Hosted checks: all nine aligned RCH checks pass on 48c4f3f; daemon unit/quality/build and independent interoperability pass on bbde8f2c. HIL remains running before publication of rch241.2.
- Publication: daemon-only testing scope; no new RCH release and no merge authorization for PR #240 or #654. Keep prior release assets and stable v0.13.0 unchanged. Independently verify the public source tag, archive, checksum, exact contents and executable after publication.

## Preserved-state finding and proposed daemon slice

The optimized repaired RCH server was restarted against the original baseline database and identity, with cursor 1024 preserved. New daemon instances reset their event sequence while retaining the same identity-based cursor scope. Successful empty polls returned cursor 1024 unchanged; newly delivered messages and announces remained invisible until the new sequence could catch up. A subsequent hot daemon restart reproduced the same condition. This is distinct from the readiness stall.

Proposed owner correction: in the daemon's existing SDK poll handler, reject a decoded cursor above the existing process sequence counter with the existing SDK_RUNTIME_INVALID_CURSOR error. RCH already recognizes that error and clears its persisted cursor. Preserve valid idle polls at the assigned high watermark, expired-cursor behavior, authorization and SDK defaults. Concurrent insertion can reorder retained entries, so the retained log tail is not an authoritative bound. Add real RpcDaemon regressions for a same-identity restart with a populated log and an empty log, reset-cursor recovery, and a valid cursor above a reordered retained tail. This restores continued imports; it does not promise replay of all events lost across restart. Qualify preserved state and hot restart before release. PRE review is required for this slice before implementation. No runtime-epoch redesign or new recovery path.

PRE review correction incorporated: use sdk_next_event_seq, never the retained tail; read and drop its guard before acquiring the event-log guard. Restart regression fails before the change. Validation is active.

Checkpoint: daemon correction committed/pushed as 75b245bf in LXMF-rs PR #654; correctness and maintainability review passed. All 756 RPC tests, 242 SDK unit tests and selected integrations, strict affected-package lint and diagnostics scanner passed. The exact stripped daemon recovered two new messages across preserved-state start and hot restart; normal shutdown. RCH pins/build references now align to that revision, and the aligned Rust 1.88 server release-readiness gate passed. Final paired 30-minute candidate qualification and daemon hosted checks remain active. No full production-stall repair claim.

## Preserved policy restoration finding

The exact paired candidate again stopped at cursor 1024 while readiness remained healthy. A persisted Reject runtime snapshot was reloaded by identity operations after successful DropOldest negotiation, because negotiation updated memory only. Configure also applied a patch/revision before restoring the older snapshot. The bounded owner correction is to restore under the existing domain lock before mutation and hold that lock through persistence; scoped config/revision guards must be released before snapshot building. PRE review passed with apply→domain ordering for configure and domain→config ordering for negotiation. Regressions seed opposite policies, negotiate or configure, restore through an identity operation and verify bounded tail retention plus saved config/revision. Preserve the failed candidate evidence; rebuild and rerun the exact pair after this correction. This remains distinct from the production readiness stall.

Checkpoint: saved-policy correction committed/pushed as d37d39b2 in daemon PR #654. PRE and POST correctness/maintainability reviews passed. All 758 RPC tests, 242 SDK unit tests and selected integrations, strict affected-package lint, formatting, boundaries, module size and diagnostics scanner pass. The RCH pin now targets this revision. Its first aligned release-gate attempt hit the unchanged inbound chat timestamp assertion; isolated retry and full workspace retry passed. The aligned optimized RCH build and HTTP smoke passed; corrected packaged-artifact qualification is running. The failed first candidate remains saved separately.

Final testing checkpoint: d37d39b2 exact stripped artifact / aligned RCH completed 30 minutes with 9034 events, 11358 polls, four fresh Delivered and persisted messages, two cursor resets, late authenticated announce and all owned/retired processes exiting zero. Only readiness interruption was the intentional daemon restart. The independent verifier validates receipt and persistence timestamps, both mature cursor-progress phases, health outside restart and source/binary binding. Both source heads' hosted checks passed, including daemon HIL and independent interoperability. The requested daemon-only testing release target is reticulumd-test-0.13.0-rch241.1; production readiness-stall diagnosis remains open and this evidence does not close the full issue.

## Storage contention and reactor starvation slice

The exact published d37d39b2 daemon, confined to two CPU slots and two Tokio
workers, lost readiness during a controlled three-second SQLite BEGIN IMMEDIATE
lock while a real TCP peer sent announces and propagation maintenance ran every
second. Eight external 250 ms readiness probes timed out and the authorized
identity announce RPC exceeded its two-second deadline. Readiness, RPC and
announce persistence recovered after lock release; every owned process exited
normally. The shortened maintenance interval and disposable state deliberately
exercise the contention boundary; this is not a reproduction of the production
topology or its original trigger. Evidence is retained separately under
/tmp/rch241-readiness-contention/run-3.

The existing announce consumer waits synchronously for its storage writer from a
Tokio worker while retaining a destination guard. The maintenance task also
performs synchronous SQLite work on a Tokio worker. Proposed correction: release
the destination guard after copying announce metadata, and await one
spawn_blocking operation for the existing sequential announce persistence calls.
Await propagation maintenance through spawn_blocking as well. Preserve the
current persistence owner, announce ordering/backpressure, non-overlapping
maintenance schedule and operator-visible errors. No storage-policy, lock-owner,
timeout or authorization changes. PRE review must pass before implementation.
Repeat the same actual-daemon contention regression, add a durable regression
through these owners, run affected daemon checks and hosted CI, then rebuild and
independently verify a new daemon-only testing candidate. Do not replace the
published rch241.1 assets or infer the undisclosed production trigger is solved.

Storage checkpoint: PRE and POST correctness/maintainability reviews passed.
Daemon commit bbde8f2c preserves sequential persistence and non-overlapping
maintenance through awaited blocking workers. The actual-binary regression
failed before the change and passes afterward, including newer persisted
identity timestamps and graceful shutdown. The stripped rch241.2 candidate
passed the same three-second contention probe with 158/158 ready responses,
20 successful polls (maximum 54 ms), resumed persistence and all process exits
zero. Affected daemon tests, strict all-feature lint, formatting, architecture
boundaries, module size and diagnostics scanner passed. RCH pins now align to
this revision and its Rust 1.88 server release gate passed. Hosted checks and
updated exact-pair sustained qualification remain pending before publication.
