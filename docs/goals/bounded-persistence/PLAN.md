# Bounded message residency and command persistence implementation plan

**Intent:** Address issues #252 and #255 without discarding history or changing command authority.
**Current Behavior:** Recent server presentation is count/byte bounded, but startup decodes a count-only window, age is unbounded, and command transactions clone entire registry/checklist collections.
**Expected Outcome:** SQLite owns history and delivery recovery. Recent presentation has count, estimated-byte and inactive-age bounds. Mutations hydrate only their command read set and persist only changed rows.
**Target-Perspective Output:** Large historical fixtures retain identical paged history while resident bytes plateau; one-entity commands remain independent of unrelated historical collections.
**Truth Owner:** SQLite for persisted history, command results, audits and delivery intents; existing core handlers for domain validation and event payloads.
**Contract Boundary:** HTTP/bridge/ordered broker inputs enter one SQLite write reservation; publication follows commit. Full export readers remain explicit compatibility operations.
**Cutover:** Command-aware transactions replace broad production mutation loaders. Broker publication applies deltas instead of replacing projection maps.
**Displaced Path:** Whole-registry/checklist snapshots in ordinary command and inbox mutation. Legacy broad transaction constructors may remain only as explicit compatibility/test adapters.
**Value Density:** Reuse domain handlers over selected aggregates and existing keyed delta writers; avoid duplicate validation implementations.
**Acceptance Evidence:** Restart/history/late-receipt/retry tests, scoped mutation parity/cascade/rejection/concurrency tests, keyed query plans, measured allocation and historical soak, workspace checks and committed readiness runner.
**Evidence Lane:** Deterministic SQLite and local runtime fixtures. Real mesh and physical hardware are outside this task.
**Kill Criteria:** No production ordinary command uses broad command snapshot loaders; no partial hydration replaces entire cache maps; no historic terminal messages are decoded just to initialize runtime cache.
**Architecture Slice:** Core SQLite command hydration/indexes, server message presentation and persistence adapters, bridge durable command entry, diagnostics and focused tests.
**Plan Review Gate:** Requires PRE review before execution.

## Ordered tasks

1. Core command selection: add keyed dependency selection under BEGIN IMMEDIATE, retain atomic command result/audit delta persistence. Add indexes for previously payload-only relationships; every writer must keep them authoritative. Allowed: core persistence modules, migration and Cargo rusqlite feature if needed. No UI, LXMF pins or release workflow changes. Evidence: unrelated history independence, cascade and payload parity, keyed plans.
2. Cut over HTTP, bridge and broker command entry; hydrate multiple envelopes incrementally without overwriting staged mutations. Publish row deltas and tombstones under existing projection-before-database lock order. Evidence: concurrent writes, rejection rollback, broker replay and multi-envelope tests.
3. Runtime cache: use operator-confirmed count/bytes/age policy, byte-aware bounded startup selection, durable point reads and diagnostics. Active delivery states stay in durable worker units rather than enlarging presentation residency. Evidence: large terminal history, older pending work, restart, late receipt and cache eviction.
4. Validate and review: formatting, strict Clippy, workspace tests, readiness runner, allocation/history soak and independent correctness/maintainability/POST plan review. Record measured limits honestly; do not substitute short fixtures for production soak claims.

Implementation tasks are sequential and owned by the main agent. Read-only architecture and review roles may run separately. Publication requires the user's separate PR/push request.

## Hydration and index contract

Use ordinary indexed scalar relationship columns derived from the MessagePack record, keeping SQLite tools usable without application-defined functions. A streaming, backed-up schema migration initializes existing rows. Central delta upserts and compatibility snapshot writers update projections within their transaction; direct client/attachment writers must be audited. Missing optional values become SQL NULL; malformed payloads fail migration or relevant reads visibly. Never infer absence from decode failure.

Each family selects these dependencies: client lifecycle selects its source (leave includes subscriptions); topics select target/subscribers and deletion attachments; marker/zone select target; missions select target, ancestor chain, direct children and marker/zone links (requested expansions add their actual collections); logs/changes select target and mission; EAM selects callsign/member collisions and referenced team/member; teams select target/mission links and deletion members; members select target/team/client links and deletion assets/skills; assets select old/new member/team/mission ownership and deletion assignments including payload asset references; skills select the target skill/member/task relation; assignments select target, task/checklist/mission/member and asset references; rights select persisted mission and subject; checklist templates select their columns/references, and checklist mutations select the affected task/column/cell/publication aggregate plus deletion requirements/assignments/asset links.

Authorization hydrates the source's member/client identities, capabilities, grants and explicit denies and validates REM team scope. Aliases, nested patches and existing row references seed dependencies. Incremental broker hydration merges original rows into the transaction without replacing previous staged changes. Collection commands deliberately select their requested collection, never a broad whole-state fallback. Tests cover each family, cascade payload parity, corruption boundaries, indexed plans and decoded-row/allocation invariance.
