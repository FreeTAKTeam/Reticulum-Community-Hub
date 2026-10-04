# Recover inbound ZeroMQ event polling Implementation Plan

**Intent:** Fix RCH issue #238 in RCH and LXMF-rs.
**Current Behavior:** SDK connection/handshake happens before its request timeout; a missing daemon can hold RCH's actor for the socket default of 30 seconds. The daemon response writer sequentially connects to client endpoints without an application deadline, letting a departed client block all subsequent responses.
**Expected Outcome:** Every SDK request has one bounded deadline covering lock acquisition, connection, command send and correlated response. A stalled response endpoint cannot block healthy daemon clients. RCH imports events again after daemon recovery.
**Target-Perspective Output:** Repeated bounded failures while the daemon is absent, then successful announce/message event polling without restarting RCH; healthy polling despite an abandoned response endpoint.
**Truth Owner:** LXMF SDK owns socket/request correlation and deadlines; reticulumd owns response scheduling; RCH owns its actor lifecycle and event imports.
**Contract Boundary:** Existing SDK v2.6 RPC/envelopes, session/request correlation and configured response endpoint remain authoritative.
**Cutover:** Replace unbounded SDK connection path and sequential unbounded daemon response writer in place; pin RCH to the reviewed upstream fix.
**Displaced Path:** Duplicate synchronous RPC implementation delegates to the canonical async implementation; remove unused response socket map.
**Value Density:** Small transport-boundary fix and integration regressions, with no new protocol or worker abstraction.
**Acceptance Evidence:** Regressions fail before fixes; socket-level SDK reconnect and daemon healthy-client isolation tests pass; RCH actor reports explicit queue expiry, permits bounded negotiation plus three identity-restore RPCs plus the requested operation, and polls successfully after unavailable-daemon startup and imports announce/message events; mandatory Rust checks pass.
**Evidence Lane:** Deterministic local TCP/ZeroMQ fixtures plus real daemon integration where available. External production network/hardware is not required for this transport regression.
**Kill Criteria:** No alternate HTTP fallback, dependency on dirty sibling files, silent dropped failures, arbitrary timeout inflation, or protocol changes. Revise scope if reproductions do not establish the proposed stalls.
**Architecture Slice:** SDK backend/zmq_pipeline.rs, transport.rs and focused tests; daemon zmq_rpc_loop.rs and response writer module/tests; RCH manifests/lock, transport actor regression, issue notes. Preserve design-qa.md and all primary LXMF checkout changes.
**Plan Review Gate:** Requires PRE review before execution.

## Ordered tasks

1. Main: add bounded socket regressions in LXMF SDK transport tests and daemon response writer tests; run with external test timeout to establish baseline stalls. No other crate changes. Parallel safe: no. Evidence: timeout/failure before fix.
2. Main: unify sync/async RPC transport, hold pipeline response endpoint and socket ownership through request, use one request deadline including connection and lock wait, reset failed transport while owned; bound daemon response delivery and concurrency using existing Tokio primitives. Files: named SDK and daemon transport modules only. Depends on 1. Parallel safe: no. Evidence: focused SDK/daemon tests, fmt, package clippy/tests, boundary/module-size checks.
3. Main: commit and push focused LXMF fix, pin RCH SDK/core consistently to its exact commit/version; add RCH unavailable-daemon then recovery/import regression and document required daemon fix for old deployments. Files: crates/r3akt-rch-server/src/lib.rs and tests/issue_238_live.rs (import acceptance and fixture budget), scripts/local-reticulum-live-gate.ps1 (run the new acceptance in the existing gate), Cargo.toml, Cargo.lock, transport Cargo.toml/lib.rs, README.md, docs/rust-transition.md, .github/workflows/{rust,rust-pr-quality,rust-release}.yml config/lxmf-runtime-baseline.json, docs/rust-migration-status.md, docs/release-readiness-audit.md, docs/issue-238-inbound-zmq.md, packaging/README.md and goal package. Depends on 2. Parallel safe: no. Evidence: workspace fmt/clippy/tests, actual ZeroMQ recovery/event fixture, local daemon integration.
4. Reviewer: PRE/POST contract review, correctness, maintainability and verification; main fixes material findings. Evidence: recorded findings and required check outcomes. Create focused PRs and attach both, without publishing a new release or merging.

## PRE review

Aligned, no blockers. Explorer confirmed zeromq 30-second connect/handshake default and the global writer stall. Required precision: explicit queue expiry, compound identity-recovery budget, shutdown cancellation with stalled peers, and real wrong-correlation filtering regression. Main will capture those checks before POST review.

## Execution and acceptance

Tasks 1–3 implemented sequentially by the main agent. Baseline regressions
failed before the fix; the SDK handshake, daemon response isolation and RCH
compound restoration failures all passed after correction. Queue expiry returns
an explicit error. Review identified daemon blocking-dispatch ownership during
shutdown; tracked, bounded RPC workers now finish before loop return, with a
controlled regression. The synchronous duplicate RPC path is removed.

The RCH slice added the import acceptance fixture and used the existing live
runner; its test-only RPC budget now includes cold handshakes. Current baseline
configuration, CI, manifests and deployment documentation use the same immutable
patched revision. Published preview.11 records retain their original baseline.

See `docs/issue-238-inbound-zmq.md` for the checked outcomes: 689 RCH workspace
tests, strict clippy, optimized server build, three-daemon receipts/fanout, 500
messages delivered, and real same-process daemon recovery followed by persisted
announce/message imports. Final POST alignment, correctness, maintainability and local verification review passed with no important remaining finding. No release publication
or merge is part of this bug-fix task.
