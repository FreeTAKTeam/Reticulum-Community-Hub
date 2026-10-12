# Bounded browser chat and indexed persistence Implementation Plan

**Intent:** Fix RCH #253 and #256 while preserving durable history, delivery state and shared Vue/Python compatibility.
**Current Behavior:** Live chat appends a single unbounded array and renders every retained message; SQLite deletes/inserts message rows, lacks normalized uniqueness, and attachment detachment already uses topic projections from PR #266.
**Expected Outcome:** Configurable bounded per-conversation/global UI retention, reachable older server history, bounded virtual DOM, indexed stable message upsert and atomic duplicate-safe migration.
**Target-Perspective Output:** Operators scroll and page older conversation history, see pending/delivery updates and clear capacity/errors; maintainers inspect query plans, preserved raw migration payloads and measured browser resource samples.
**Truth Owner:** Rust/Python backend owns message/delivery/attachment records. UI owns only bounded presentation, pagination coordination, drafts, viewport and configuration.
**Contract Boundary:** Existing /Chat/Messages array response remains compatible. Add an explicit Rust /Chat/History page endpoint returning Messages and NextCursor, authoritative scope/peer filtering, and stable cursor using creation timestamp plus integer rch_messages.id, ordered created_ts_ms DESC,id ASC. Python legacy initial lists remain supported; unavailable older paging is explicit.
**Cutover:** Replace growing store array with one bounded cache, preserving a derived compatibility messages view. Replace ChatPage v-for with a measured variable-height message viewport. Central message writer uses ON CONFLICT against NOCASE uniqueness and preserves row ID.
**Displaced Path:** Unbounded append/fetch replacement and full DOM removed; delete/insert writer removed; no parallel history truth or client delivery rule engine.
**Value Density:** Reuse Vue/Pinia, existing API/WS and preview cleanup, SQLite relationship projections and installed dependencies. No new libraries.
**Acceptance Evidence:** Store policy/race/lifecycle tests, authenticated history pagination responses, indexed query-plan/migration/upsert tests and DB/WAL comparisons; browser WebSocket replay, heap samples, DOM counts while paging/scrolling, screenshots and focus checks; full required UI/Rust checks.
**Evidence Lane:** Deterministic local fixture/runtime/browser, not physical devices or production-duration mesh.
**Kill Criteria:** Reject wrong frontend domain owner, weakened bounds/tests, silent unsupported pagination, unbounded tombstones/height maps/previews, stale backend publication, raw-payload loss or unlocked read/write migrations.
**Architecture Slice:** ui/src/config/chat-retention.json + validated config module; api/chat adapter; stores/chat-window presentation cache; stores/chat.ts coordinator; components/chat/ChatMessageList.vue viewport + card; ChatPage wiring; core sqlite message migration/history/attachment helpers; server additive chat history route; tests and goal evidence docs. Avoid dependency pins, Python branch, release packaging, unrelated UI and sibling checkouts.
**Plan Review Gate:** PRE reviewed independently; concrete cursor, pending capacity, live revision, expiry, auth disposal and migration evidence corrections recorded below. Approved for independent UI/history work; duplicate resolution remains gated.

## Policy and dependencies

Base is PR #266 head eb60dd6; new branch corvo/issues-253-256-chat-indexes. Keep PR #266 unmodified. User approved configurable 200/conversation, 2000 global, 16 MiB and 30-minute inactivity. Values reside in JSON configuration with validated VITE_CHAT_* overrides, not inline cache constants. Pending outbound remains protected; new sends reserve conservative content/attachment byte and count capacity before request, accounting for response growth and clearly fail before network when full. Tombstones/page/viewport bounds are configured too. Existing pending records and send reservations are never evicted. Incoming remote overflow is visibly rejected from the presentation window while remaining durable on the backend. Unknown ancient live events cannot rehydrate evicted history after bounded tombstones expire; explicitly requested historical pages may replace a conversation window. Wire UpdatedAt currently equals CreatedAt, so history requests preserve live sequence updates after request start and never infer delivery freshness from it. Age uses activity; maintenance is owned by the store while Chat is mounted and disposed on scope/auth loss or unmount. Auth revocation clears all private bookkeeping even when requestIdentity is unchanged. User duplicate migration policy is pending; do not execute duplicate resolution before answer.

## Tasks (main implements sequentially)

1. Core indexed writer/migration: add schema 7 normalized unique identity with bounded streaming backfill, archive-or-reject duplicate policy per user answer, retained payload bytes and stable row ordering. Maintain authoritative scope/source projections, justified composite indexes, bounded streaming matching-only attachment detach using actual topic/category queries, with no invented mission projection. Verify populated migration restart/rollback, query plans and write amplification.
2. History boundary: additive /Chat/History endpoint with validated scope/peer/cursor, indexed stable keyset pages and explicit nonpersistent fallback; original /Chat/Messages untouched. Verify equal timestamps, interleaved new inserts, scope/peer filters and endpoint payload.
3. UI cache/config/adapter: separate wire validation and configured cache from store orchestration. Bound count/bytes/age/tombstones/conversation bookkeeping. Protect pending; use backend updates, preserve success against stale failure and scope assertion on read/send/upload; clear on auth revocation. Verify sustained events, duplicate, delivery, exhaustion, old-page and stale races.
4. UI viewport: extract message card/list with ResizeObserver variable-height virtualization, bounded measurements and viewport-only attachment previews; older/newer window controls and preserve reading/scroll anchor. Scope switches fetch chosen conversation; streams restart/close immediately. Verify DOM, keyboard, pagination, attachments and route cleanup in real Chromium.
5. Gates: npm ci (locked installed cache), UI lint/typecheck/test/build/e2e, fmt/clippy/workspace tests and server-only readiness for changed server; record measurements and limits. Independent correctness/maintainer/POST review before commit. Do not push or create PR unless requested for this new task.

## Design references

Vue's official performance guide recommends list virtualization and shallow reactivity for large immutable structures: https://vuejs.org/guide/best-practices/performance.html . Use measured heights rather than truncate messages into fixed-height cards; this adds one viewport owner instead of a new library. SQLite UPSERT is keyed by a uniqueness constraint: https://www.sqlite.org/lang_upsert.html ; ASCII NOCASE matches hex message IDs: https://www.sqlite.org/datatype3.html . Keep payload casing intact and use COLLATE NOCASE in point reads/conflict target.

## Final task status

Tasks 2–4 and measured task-1 identity/index/backfill/detachment work passed local
acceptance and independent correctness/maintainer/POST review. Task 5's UI, full
Rust workspace and committed server-only readiness checks passed. Existing
case-insensitive duplicates still stop schema-7 migration with all rows preserved;
final archive-or-reject policy remains awaiting the user. No duplicate resolution,
commit, push or new PR has been performed.
