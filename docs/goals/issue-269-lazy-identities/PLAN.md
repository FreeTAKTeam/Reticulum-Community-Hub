# Demand-driven identity directory implementation plan

**Intent:** Fix #269 without deleting identities or announces.
**Current Behavior:** Shared UI drains every identity page. Rust clones all states and hydrates every annotation before slicing.
**Expected Outcome:** Dashboard/Chat/Topics request only needed identity enrichment; opening Identities requests one server page. Search, Recent/All history, type and page controls replace bounded results.
**Target-Perspective Output:** With 15,000 identities/100,000 announces, an operator sees current directory results, can find old saved/moderated identities and navigate history without downloading the complete inventory.
**Truth Owner:** SQLite core records and their transactionally maintained directory read model; server owns query policy and compatibility. UI owns query coordination and display.
**Contract Boundary:** Existing `/Identities` legacy array and page envelope retained. Opt-in `view=recent|all`, `search`, `identity`, `client_type=all|rem|generic_lxmf`, `order=identity_asc|last_seen_desc` query fields. Exact normalized identity lookup also matches advertised destination. Existing payload keys preserved; additive `RecentlyHeardAt` describes maximum announce age, separate from preferred annotation metadata and presence.
**Cutover:** Use one indexed SQLite directory read model for persisted page/filter queries. Keep full legacy response and explicit in-memory runtime support. Remove identity hydration from `fetchUsers`, retire concatenated identity history state and local history filtering.
**Displaced Path:** Automatic identity continuation loop, global full identity array, full-server per-page payload hydration. Existing client roster and REM behavior remain independently owned.
**Value Density:** Page-bounded payload decoding and browser residency replace historical full materialization; no transport/protocol rewrite.
**Acceptance Evidence:** Rust DB/API legacy/alias/moderation/annotation tests, realistic indexed fixture query plans and release measurements; Pinia/Vue cancellation/page/navigation/consumer tests; actual browser UI and real-backend request evidence.
**Evidence Lane:** Synthetic local fixtures and bounded browser/runtime checks; no production-duration/HIL claims.
**Kill Criteria:** No startup directory crawl, no automatic identity continuation, no unbounded directory concatenation/cache, no announce-history deletion, no new UI authority for recency/moderation.
**Architecture Slice:** Core directory query/projection module; migration/write hooks in existing SQLite modules. Small server query module and route/OpenAPI/app-info integration. Cohesive identity adapter/query store and Users directory component; scoped consumer enrichment in dashboard/chat/topics. Preserve unrelated worktrees, dependency pins, telemetry, transport and command workers.
**Plan Review Gate:** Requires PRE review before execution.

## Policy and compatibility

User approved configurable defaults: page size 50, Recent window 24 hours; include joined, team-linked, REM and moderated identities even if stale. All history retains every record. Configuration must be documented and validated, with settings exposed through app info for the UI. Normalization uses existing Rust trim/ASCII lowercase. Preferred annotation remains first raw destination with destination-source priority; directory recency is maximum last-heard timestamp. Voice exclusions occur before totals and pagination, including owner clients absent from identity-state rows. Lookup failures must not block unrelated views. Legacy Python cannot supply searchable server paging: report the unsupported capability explicitly rather than draining/retaining its full directory; retain ordinary Users/Chat/Topics operation.

## Tasks and verification

1. Core read model (parallel, core-only): add migration with backup and incremental write maintenance covering announce, identity, roster/team/mode/snapshot/import paths. Preserve original records. Public `IdentityDirectoryQuery` has search/identity/client_type, recent cutoff, newest-first, offset/limit and normalized voice exclusions. `IdentityDirectoryPage` has total and entries containing state, preferred announce, REM mode and last-heard timestamp. Add semantic and 15k/100k query-plan/limited-decode tests. Run focused core tests, fmt/clippy.
2. Frontend (parallel, UI-only): lazy identity page adapter/store/component, configurable defaults from app-info, abort/generation/backend guards, bounded exact lookup enrichment. Remove eager startup identity paths. Preserve visible labels, moderation/join actions, roster/member selectors and presence evidence. Add mock/Pinia/Vue regressions; run UI lint/typecheck/test/build and browser acceptance.
3. Server integration (root, server/docs-only): opt-in query validation/config and app-info/OpenAPI, use core read model before payload assembly and spawn blocking work; preserve legacy/in-memory semantics and voice suppression. Add API regression tests. Run focused server tests, workspace fmt/clippy/tests.
4. Integrate: run full UI checks and applicable Rust gates, capture before/after bytes/latency/decoding/residency and browser request evidence on realistic fixture. Record limits and avoid claiming unperformed client/hardware acceptance. Do not publish a PR or release without a new user request.

## PRE corrections and execution contract

PRE review identified effective runtime metadata, lookup bounds and presence gaps. Follow-up source inspection confirmed display/voice fields are not persisted in CoreClientRecord and have no production voice producer; adding a second persisted voice authority is unnecessary. Server takes normalized scalar actual-roster overlays (no full client payload clone/history hydration), SQL applies custom names and voice exclusions only when the owner has no preferred annotation and qualifies for the current client list, and only selected page clients are cloned for final payload overlay. This preparation is O(actual roster size), explicitly separate from historical identity/announce inventory. Regression cases cover annotated names replacing custom names, annotation clearing voice suppression, and voice owners absent from identity states.

Lookup presentation configuration defaults to 500 retained entries and four concurrent requests, validated and exposed by the server alongside page size and recency. Normalize/deduplicate keys; invalidate on backend/credential switches, explicit refresh and identity mutation; abort obsolete requests and bound event-driven growth. Each consumer enriches only its visible IDs; errors remain independent. RecentlyHeardAt and legacy discovery Status cannot alone label a peer online.

Opt-in filters without page parameters return the existing array shape, but perform SQL filtering first. UI always sends explicit page/per_page. Exact identity lookup accepts normalized canonical identity or advertised destination and returns the canonical identity; voice destinations suppressed by a distinct owner do not become separate rows.

Acceptance invariants: initial Identities page <= configured size and one page request; no automatic continuation; retained directory <= configured page size and lookup cache <= configured cap; <= page size state/announce/REM payloads decoded in a page; no deletion of the 15k identity / 100k announce fixture; correct filtered totals/order; stale query/backend results never publish. Measure latency/bytes/memory without inventing a universal timing SLA.

PRE major findings corrected as above; review concluded the scalar-overlay approach is the smallest safe design. Execute the parallel disjoint core/UI tasks and root server integration, followed by integration and POST/correctness/maintainability verification.

Research: existing Vue/Pinia request facilities suffice for a feature query owner; use watcher cleanup and AbortController instead of a second HTTP stack (https://vuejs.org/guide/essentials/watchers.html, https://pinia.vuejs.org/core-concepts/). SQLite composite indexes support stable ordering and keyed relationship probes (https://sqlite.org/queryplanner.html); substring search/count may scan scalar directory rows, while payload decoding stays page bounded.

## Completion

All four tasks are complete locally. POST findings were corrected; integration
also fixed narrow-window overflow and preserved Unicode name-search behavior.
See EVIDENCE.md for terminal checks, real browser/API acceptance, measurements and
remaining compatibility costs. No publication was performed.
