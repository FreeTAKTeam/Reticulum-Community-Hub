# Issue 247: SDK-owned outbound transport

## Outcome and authority
A send to one destination costs independently of announce-history size. RCH selects application recipients; LXMF-rs owns paths, next hops, interfaces, transport methods, fallback and admitted delivery terminality. The requested destination is preserved. Compatibility with RCH's incorrect strategies is explicitly waived by the user.

## Contract and cutover
The existing negotiated ZeroMQ SDK actor queries `RnsTransportOperation::PathStatus` for each distinct outbound destination and requests an unknown path through `RequestPath` with no synchronous discovery wait. It preserves the daemon response (including hop/interface metadata) for diagnostics and sends to the original destination through the SDK. No local routing table, history fallback, destination alias inference or path cache is introduced. Lookup errors remain visible.

Delete the announce-derived outbound delivery policy, name/voice alias routing, stale-announce rejection and direct-failure cooldown. Use the SDK default delivery request with daemon propagation fallback, retaining recipient idempotency. Remove local receipt terminal deadlines, synthetic pending status and method-changing timeout repair. Remove automatic first-known-node selection. Explicit operator controls remain operator controls; no replacement selection heuristic is invented.

Application-owned topic/subscriber/client roster, exclusions, allowlists, moderation, REM encoding, persistence and pre-admission scheduling remain. Announce history remains application data. Confirmed retryable SDK rejections remain durably queued; admitted or uncertain recipient IDs are reconciled without resubmission. Permanent rejection evidence survives later recipient retries.

## Evidence and kill criteria
- A database with 100,001 announce rows, including malformed unrelated payloads, must not be decoded or scanned by targeted outbound selection/admission. Same-name announce entries cannot redirect the destination.
- Typed SDK wire tests prove destination-keyed status, missing-path request and unchanged destination submission. Known paths do not request discovery; malformed/rejected responses fail visibly.
- SDK terminal failure remains terminal. An admitted active delivery remains reconcilable beyond the old local deadline, without resubmission.
- Disposable real daemon/SDK run compares path status metadata and verifies path request plus receipt delivery where a local peer is available.
- Required workspace formatting, clippy and tests pass. Report external/hardware evidence separately.
- No compatibility shims or second transport strategy survive. If the pinned SDK lacks a required operation, stop that cutover and document the demonstrated API gap.

## Execution board
1. Explorer: map current outbound and receipt strategy owners (complete).
2. PRE plan review: validate owner/cutover/evidence before implementation (complete).
3. Main: remove strategies; add typed SDK path resolution and regressions (complete).
4. Verifier: run required checks and disposable runtime evidence (complete; see EVIDENCE.md).
5. Reviewer/maintainer/POST: inspect correctness, duplicate paths and plan alignment; repair findings (complete).
6. Commit, push and create reviewable follow-up PR; do not merge or publish a release in this task.

## PRE clarifications
- Remove first-node selection in both startup and `/Control/Sync`. Sync uses the daemon-selected node through SDK controls and returns an error if none is selected; it never changes that selection.
- Accepted recipient IDs are never resubmitted. Ambiguous admission retains the original request and correlation/idempotency key for SDK reconciliation. Only confirmed retryable pre-admission rejections are automatically scheduled. Remove generic error-text transport retry classification rather than retaining it as a compatibility strategy.
- Previously queued rows pass through the same SDK-owned default request. Persisted cooldown/fallback hints cannot reactivate a transport strategy. Keep recipient keys stable and do not alter completed history.
- Test both a single target and explicit recipient lists against 100,001 history rows.
