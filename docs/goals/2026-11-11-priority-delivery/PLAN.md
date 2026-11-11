# Bounded SDK sessions and remaining authentication hardening

**Intent:** Deliver the highest-value actionable reliability and security slice of [roadmap #279](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/issues/279) on 11 November 2026, using one SOL agent and one PR per implementation issue.
**Current Behavior:** RCH's allocation parser repair is already merged in #310. The daemon still retains abandoned negotiated SDK sessions until its 4,096-entry limit is reached. RCH #231's environment sample, public setup redaction and cited PostCSS advisories are already addressed; legacy credentials still need visibility before use.
**Expected Outcome:** Abandoned SDK sessions are reclaimed without losing durable custody or interrupting active clients; RCH uses the matching SDK/daemon and recovers after retirement; operators see a safe startup warning while legacy credentials await their existing successful-verification migration.
**Target-Perspective Output:** A hub operator can restart clients repeatedly against one daemon, continue durable message processing, inspect aggregate session counts and see actionable credential warnings without exposed secrets. Three individually reviewed PRs contain reproducible evidence and pass their applicable checks before merge.
**Truth Owner:** LXMF-rs owns authenticated session lifetime and durable broker state; RCH's existing transport actor owns service-identity restoration; RCH auth/SQLite settings own credential verification and migration.
**Contract Boundary:** Authenticated ZeroMQ negotiation/session identity, broker admission/replay/custody and RCH adapter recovery; public setup status versus authenticated or trusted local bootstrap details.
**Cutover:** Merge the upstream session PR, then update all RCH dependency/runtime/workflow pins together. Keep existing credential upgrade-on-success behavior and add startup visibility only.
**Displaced Path:** Negotiated session entries no longer live forever. Existing negotiation and actor recovery remain the sole recovery paths; no parallel registry, auth database, retry worker or mesh protocol is added.
**Value Density:** Fix the unaddressed cause of permanent session exhaustion behind the newest production incident, carry it through the actual consumer, and finish a small independent M0 security issue.
**Acceptance Evidence:** Deterministic lifecycle/custody regressions, real ZeroMQ request/response and paired restart/recovery evidence, exact redacted setup responses and nonmutating legacy-credential detection, reviewed exact PR heads and passing CI.
**Evidence Lane:** Local software and controlled integration. Production deployment, private incident replay, hardware/field qualification and multi-hour resource acceptance are separate claims.
**Kill Criteria:** Do not duplicate merged parser work; do not evict live sessions to make room; do not erase identities, custody, checkpoints, operations or credentials; do not call daemon-wide shutdown to close one client; do not mark the broader resource gates complete from short tests.
**Architecture Slice:** Daemon session registry and SDK negotiation, RCH transport session/recovery and pinned runtime manifest, auth startup and existing setup tests.
**Plan Review Gate:** Independent SOL PRE review: aligned, no blockers. Its required same-actor expiry recovery case and expiry-only diagnostics correction are included below. POST/correctness/maintenance review follows at the final heads.

## Verified starting point

- RCH main: `d2bcedabad354e11e9a1bad9cea5e37af24441e9`.
- RCH paired LXMF revision: `9b972f9a8d3a7949eae89bc78f7a9691f06f3ed1`; SDK 0.16.1, contract v2.6, Rust minimum 1.89.
- LXMF-rs main: `ec4881e6c40bffd4a49ac4c40259bc531cef6cd6`.
- No open PRs were present in either repository at discovery. LXMF #719 is closed; former PRs #734/#736 are no longer open.
- RCH #310 already bounds capability decoding and tests the incident-equivalent array count. Its initial hotfix has bounded historical production evidence; that does not qualify today's new pair.
- The main LXMF checkout has unrelated edits. All work uses new isolated `corvo/` branches/worktrees and preserves existing worktrees.

## Assignments and order

| Order | SOL owner | Issue / PR | Allowed write scope | Dependency |
|---|---|---|---|---|
| 1 | `lxmf_755` | [LXMF #755](https://github.com/FreeTAKTeam/LXMF-rs/issues/755), one upstream PR | Existing RPC session types/handlers, SDK session lifecycle if needed, focused tests and owning contract/status docs | PRE-approved lifecycle design |
| 1 | `rch_231` | [RCH #231](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/issues/231), one hardening PR | `crates/r3akt-rch-server/src/auth.rs`, owning startup/settings path, auth/setup tests and auth operations documentation | Independent of session work |
| 2 | `rch_307` | [RCH #307](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/issues/307), one integration PR | Root Cargo manifests/lock, all `LXMF_REF` workflows, runtime baseline, transport actor only where required, integration tests and this goal package | Final upstream contract, then merged upstream SHA |
| Every gate | Parent | Plan, correctness, CI and merge management | Review/evidence, scoped corrections and integration | Agents do not approve or merge their own work |

The first two assignments can execute in parallel. The RCH integration agent may prepare tests while upstream works, but final pinning and acceptance use the merged upstream revision. Keep all builds bounded; avoid multiple Cargo jobs contending for the same target directory.

## Task 1: retire abandoned negotiated sessions

Read every use of `sdk_identity_sessions`, session identity selection, authenticated principal context, negotiation and SDK/RCH recovery before editing. The primary boundary is `crates/libs/rns-rpc/src/rpc/daemon/sdk_broker.rs`; retain existing module boundaries and size limits.

- Use a five-minute monotonic idle lifetime and bounded reaping at negotiation/admission, diagnostics and the route's next request in the existing owner. Pin in-flight requests through response completion without holding a registry lock across execution. Only successful accepted operations refresh activity; rejected cross-principal calls must not keep another client's session alive.
- Preserve the legacy default context and live sessions. Keep the capacity limit and deterministic busy behavior when all slots are active.
- Remove only ephemeral session state. Durable operations, consumer checkpoints, stored messages, registered identities and custody survive.
- Return a recognizable session-negotiation error after expiry. Recovery reuses the existing SDK negotiation and RCH identity-restoration owner.
- Use expiry for both abandoned graceful-disconnect and killed clients; no new close API is needed for this slice. Do not call `sdk_shutdown_v2`.
- Expose aggregate current/expired counts without identifiers or credentials. Do not add a permanently-zero closed counter. Document where reaping happens and what an idle client sees.
- Verify expiry, capacity, active protection, principal isolation, repeated restart counts above 4,096, and durable/idempotent replay with a controllable clock or deterministic test-time aging. Add a real ZeroMQ lifecycle regression.

Acceptance: parent can inspect the actual negotiated request/response sequence, bounded registry counts and preserved durable records. A registry-only unit test is insufficient for the integration claim.

## Task 2: finish legacy-credential visibility

Use the same format classification as verification. At SQLite auth initialization, warn once per startup when a valid legacy password or PIN hash is present. Include no hash, salt, plaintext, identity or filesystem path. Initialization must not rewrite or delete credentials.

- Preserve successful-login password migration and successful PIN-verification migration; API-key authentication does not migrate the stored password.
- Give safe operator guidance. Do not advise arming or triggering the destructive kill switch solely to migrate its PIN.
- Tighten the existing post-enrollment public setup test to the exact minimal response. Preserve detailed authenticated and trusted local pre-enrollment bootstrap required by the shared Vue/Tauri wizard.
- Verify both legacy kinds, Argon2id and malformed/absent values, no startup writes, subsequent successful migration and exact public redaction.
- Reconcile all four #231 findings in the PR with source and advisory evidence. Do not alter the already-correct environment example, UI or lockfile for cosmetic consistency.

Acceptance: deterministic warning classification and stored-record evidence, plus actual setup route responses from the existing HTTP tests. No new credential deadline, disable flag or schema migration.

## Task 3: consume and verify the matched runtime

After Task 1 merges, pin all four LXMF workspace dependencies, Cargo.lock, every workflow `LXMF_REF` and `config/lxmf-runtime-baseline.json` to the same merged revision. Keep version/contract metadata truthful; do not invent a release tag.

- Change the transport actor only if the agreed lifecycle contract requires it. Inspect both actor lanes and legacy actor callers and preserve stop-admission, deadline and error behavior.
- Re-run the existing #307 hostile-capability replay regression against the new pair.
- Verify one running daemon across repeated graceful and abrupt client restarts, reclamation and active-client protection. Check actual durable intake/checkpoint progress and stored acknowledgements with generated local identities/data.
- Separately keep the same RCH actor/process alive across idle expiry: observe `SDK_BROKER_NEGOTIATION_REQUIRED`, then the existing bounded worker retry must reopen the session, restore the same identity, resume the existing consumer and store/acknowledge a fresh message. Restart-only tests cannot satisfy this gate. Do not automatically replay mutations with unknown outcomes.
- Use existing live-gate infrastructure for direct/fanout receipts and restart recovery where supported. Record exact source SHAs, commands, test counts and boundaries.
- Record bounded local memory/session observations without claiming a multi-hour resource pass. Keep #241/#242/LXMF #663 open unless their full independent acceptance is actually met.

Acceptance: all pins agree, real SDK/daemon session recovery works, and fresh generated messages progress through the existing durable path. A healthy HTTP listener alone is insufficient.

## Validation and PR management

1. Run focused regression tests first using an installed toolchain meeting the current 1.89 minimum and locked dependencies.
2. RCH: `cargo fmt --all -- --check`, `cargo clippy --locked --workspace --all-targets -- -D warnings`, and `cargo test --locked --workspace`; cover server/core/transport/TAK release-critical suites. Use the committed readiness runner if making a release-candidate claim.
3. LXMF: affected RPC/SDK/daemon suites, formatting, relevant architecture/boundary/diagnostic checks, then the repository-required CI gates. Do not weaken checks to make the branch green.
4. Documentation: run existing link checks and `git diff --check`. No UI build is needed unless source changes reach that layer.
5. Each agent commits only its issue files and opens one PR with reproduction, outcome, evidence, compatibility and remaining limits. Use `Closes` only for an entirely satisfied issue; RCH #307 may remain open for sustained acceptance.
6. Parent independently reviews each exact head, sends corrections to its owner, resolves verified review findings and monitors CI to completion. Re-review after material changes.
7. Submit formal approval if the available GitHub identity is eligible. GitHub prohibits author self-approval; otherwise record the independent review as a comment and merge only under existing repository rules. Do not bypass protections or impersonate a reviewer.
8. Merge upstream #755 before final #307 integration. #231 may merge independently. Use expected-head checks, then verify the merged main state and safely delete only this task's clean merged branches/worktrees.

## Boundaries

Today does not include new media/voice/BLE features, broad server refactoring, branch-protection changes, production deployment, access to private crash reports, or restarting the previously canceled synthetic allocator soak. Follow-on operational acceptance remains visible in its existing issues.

## Progress

- [x] Read current roadmap, issue states, merged repairs and repository ownership.
- [x] Create canonical upstream lifecycle issue #755 and isolated issue branches.
- [x] Complete PRE review and concrete upstream lifecycle design, including same-actor expiry recovery.
- [x] Merge the independently reviewed #231 PR: [RCH #320](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/pull/320).
- [x] Merge the independently reviewed #755 PR: [LXMF #756](https://github.com/FreeTAKTeam/LXMF-rs/pull/756).
- [x] Pin and locally verify the #307 integration against the merged upstream source; see [EVIDENCE.md](EVIDENCE.md).

This is the plan snapshot carried by the integration PR. Its exact-head hosted
checks, technical review, merge event and final cleanup report are the delivery
status; they are not inferred from this checklist. Broader incident acceptance
remains in #307 and the existing resource issues.
