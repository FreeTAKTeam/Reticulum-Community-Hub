# RCH Rust Performance Stress Report

Generated: 2026-05-17

## Scope

This report records the first repeatable speed-test pass against the live Rust
test server at `http://127.0.0.1:8081` using the real manual-test database and
the configured Reticulum runtime. The benchmark harness is
`scripts/rch-speed-test.ps1`.

Artifacts:

- `target/manual-test/rch-speed-python-baseline-20260517152011.json`
- `target/manual-test/rch-speed-rust-empty-20260517152150.json`
- `target/manual-test/rch-speed-rust-current-20260517152031.json`
- `target/manual-test/rch-speed-rust-after-status-fastpath-20260517153255.json`
- `target/manual-test/rch-speed-rust-after-event-summary-20260517155512.json`
- `target/manual-test/rch-speed-rust-after-r3akt-targeted-lists-20260517161048.json`
- `target/manual-test/rch-speed-rust-after-mission-change-summary-20260517162024.json`
- `target/manual-test/rch-speed-rust-after-readonly-open-20260517165456.json`
- `target/manual-test/rch-speed-rust-empty-after-readonly-open-20260517165642.json`
- `target/manual-test/rch-speed-rust-after-telemetry-harness-20260517165757.json`
- `target/manual-test/rch-speed-after-identity-targeted-20260517.json`
- `target/manual-test/rch-speed-after-readonly-command-20260517.json`
- `target/manual-test/rch-speed-after-attachment-targeted-20260517.json`
- `target/manual-test/rch-speed-after-checklist-readonly-20260517.json`
- `target/manual-test/rch-speed-after-r3akt-read-snapshot-20260517.json`
- `target/manual-test/rch-speed-after-checklist-template-direct-20260517.json`
- `target/manual-test/rch-speed-after-history-targeted-20260517.json`

The benchmark uses short runs during active development (`Iterations=3`,
`Warmup=1`) so values should be treated as directional, not a statistical SLA.
The latest Python comparison and status fast-path runs used `Iterations=5`,
`Warmup=1`.

## Findings

The initial stress pass showed that the perceived slowness was mostly from
server-side synchronous persistence/runtime reads rather than the browser UI:

| Surface | Before | After | Change |
| --- | ---: | ---: | --- |
| `/Client` | ~3191 ms avg, ~5815 ms p95 | ~13 ms avg, ~15 ms p95 | Removed synchronous Reticulum announce poll from UI read path and replaced full snapshot annotation load with targeted identity table reads. |
| `/Identities` | ~1092 ms avg after first partial fix | ~35 ms avg | Reused targeted identity announce/rem-mode loads. |
| `/api/rem/peers` | ~591 ms avg after first partial fix | ~13 ms avg | Replaced full snapshot load with targeted identity announce/state/rem-mode reads. |
| `/File` | ~858-1138 ms avg | ~12 ms avg | Replaced full snapshot load with category-indexed attachment query. |
| `/Image` | ~688-1064 ms avg | ~11 ms avg | Replaced full snapshot load with category-indexed attachment query. |
| `/api/r3akt/missions` | ~2112 ms avg before read-only fix | ~599 ms avg | Avoided full snapshot save for read-only R3AKT list/get commands. |
| `/api/r3akt/team-members` | ~2747 ms avg before read-only fix | ~501 ms avg | Same read-only R3AKT command fast path. |
| `/checklists/templates` | ~1912 ms avg before checklist read-only fix | ~883 ms avg | Avoided full snapshot save for checklist template list/get. |
| `/api/r3akt/missions` | ~599 ms avg after read-only save fix | ~30 ms avg | Replaced full SQLite snapshot reconstruction with R3AKT-specific read snapshot. |
| `/api/r3akt/missions/{uid}?expand=all` | ~1312 ms avg after read-only save fix | ~37 ms avg | Same R3AKT-specific read snapshot. |
| `/api/r3akt/log-entries` | ~981 ms avg after read-only save fix | ~38 ms avg | Same R3AKT-specific read snapshot. |
| `/api/EmergencyActionMessage` | ~1167 ms avg after read-only save fix | ~29 ms avg | Same R3AKT-specific read snapshot. |
| `/api/r3akt/teams` | ~1107 ms avg after read-only save fix | ~32 ms avg | Same R3AKT-specific read snapshot. |
| `/api/r3akt/assets` | ~915 ms avg after read-only save fix | ~31 ms avg | Same R3AKT-specific read snapshot. |
| `/api/r3akt/assignments` | ~826 ms avg after read-only save fix | ~28 ms avg | Same R3AKT-specific read snapshot. |
| `/checklists/templates` | ~2173 ms avg before direct template read | ~15 ms avg | Replaced checklist command path with direct template/column read model. |
| `/api/r3akt/events` | ~2021 ms avg before targeted audit query | ~454 ms avg | Replaced full snapshot load with bounded audit-event query. |
| `/api/r3akt/snapshots` | ~5005 ms avg before R3AKT snapshot read model | ~81 ms avg | Returned R3AKT state from the R3AKT-specific read snapshot instead of full runtime state. |
| `/Status` | ~64 ms avg on the manual store | ~23 ms avg | Replaced full runtime diagnostics work in the dashboard status route with a side-effect-free runtime status payload. |
| `/diagnostics/runtime` | ~57 ms avg on the manual store | ~12 ms avg | Kept the full diagnostics endpoint, but the rebuilt server run no longer showed the earlier high fixed overhead after the status split/restart. |
| `/api/r3akt/events` UI query | ~751 ms avg, 5.4 MB full payload | ~16 ms avg, 6.4 KB summary payload | Added `include_payload=false` and moved the UI-backed event fetch to `limit=25&include_payload=false`; default API behavior still returns full payloads for parity. |
| R3AKT list routes | ~24-50 ms after R3AKT read snapshot | ~11-16 ms for missions, log entries, teams, members, assets, assignments | Added targeted read models for common collection list routes instead of reconstructing the broad R3AKT snapshot for each collection. |
| `/api/r3akt/mission-changes` UI query | ~36 ms avg, 218 KB full delta payload | ~26 ms avg, 33 KB summary payload | Added `include_delta=false` and moved the UI fetch to omit large deltas by default; full delta remains the API default. |
| Read-only SQLite opens | ~11-26 ms fixed floor on many R3AKT/file/identity read routes | ~1.4-5.3 ms for most targeted manual-store reads | Added `RchSqliteStore::open_read_only` and routed pure read paths away from per-request migration setup. |
| `/Telemetry?since=0` | Previously failed in the harness because the required `since` query was omitted | ~2.1 ms avg | Corrected the benchmark harness to use the real Python-compatible route contract. |

## Python Baseline Comparison

Python RCH 2.9.6 was started from a separate local worktree on
`http://127.0.0.1:8082` with an isolated empty store and API key
`manual-test`. A second temporary Rust server was started on
`http://127.0.0.1:8083` with an empty store for a same-data comparison. The
manual Rust server remained on `http://127.0.0.1:8081` with the realistic
manual-test database.

Empty-store comparison:

- The latest Rust empty-store run is faster than Python on 21 of 26 comparable
  successful benchmark routes.
- The biggest Rust wins are the high-frequency UI and operator routes:
  `/Status` ~4.5 ms versus Python ~26 ms, `/Client` ~2.6 ms versus ~27 ms,
  `/api/rem/peers` ~3.7 ms versus ~20 ms, `/Events` ~0.6 ms versus ~5.8 ms,
  `/Chat/Messages` ~0.8 ms versus ~11.7 ms, and common R3AKT collection reads
  mostly ~1.5-3.5 ms versus Python ~6-12 ms.
- The remaining slower empty-store routes are `/diagnostics/runtime`,
  `/api/r3akt/snapshots`, `/checklists`, `/checklists/templates`, and
  `/api/r3akt/events`. These are diagnostic/export or aggregate view-model
  routes, not the LXMF-rs dispatch path.

Latest manual Rust versus empty Python directional result after the read-only
SQLite fast path:

- Rust is faster on 19 of 26 comparable successful benchmark routes while
  serving the realistic manual dataset.
- The remaining slower routes are payload-heavy or diagnostic/export surfaces:
  `/Events` returns about 748 KB, `/api/r3akt/snapshots` returns a broad state
  export, checklist aggregate routes reconstruct checklist view models, and
  `/diagnostics/runtime` intentionally performs diagnostic work.

| Surface | Python empty avg | Rust manual avg after fix | Result |
| --- | ---: | ---: | --- |
| `/Status` | ~26 ms | ~3.8 ms | Rust faster after status and read-only fast paths. |
| `/api/v1/app/info` | ~14 ms | ~1 ms | Rust faster. |
| `/Topic` | ~12 ms | <1 ms | Rust faster. |
| `/Subscriber` | ~9 ms | <1 ms | Rust faster. |
| `/api/markers` | ~6 ms | <1 ms | Rust faster. |
| `/api/zones` | ~8 ms | <1 ms | Rust faster. |
| `/Client` | ~27 ms | ~1.9 ms | Rust faster. |
| `/api/rem/peers` | ~20 ms | ~1.7 ms | Rust faster. |
| `/Identities` | ~34 ms | ~5.3 ms | Rust faster. |
| `/File` | ~7 ms | ~1.4 ms | Rust faster. |
| `/Image` | ~12 ms | ~1.4 ms | Rust faster. |
| R3AKT common collection reads | ~6-12 ms | ~1.4-2.3 ms for missions, log entries, teams, members, assets, assignments, and EAM | Rust faster on common collection reads after targeted read models plus read-only SQLite opens. |
| `/api/r3akt/mission-changes?include_delta=false` | ~8.6 ms | ~12.3 ms | Still slightly slower than Python empty-store; this is a reduced-delta UI query over real mission-change history. |
| `/api/r3akt/events?limit=25&include_payload=false` | ~7 ms | ~17.2 ms | Still slower than Python empty-store, but no longer serializes the 5.4 MB full event payload for UI reads. |
| `/api/r3akt/snapshots` | ~7 ms | ~39.9 ms | Still slower; this is an export/diagnostic state snapshot rather than a high-frequency UI load route. |

## Changes Applied

- Added `scripts/rch-speed-test.ps1`, a repeatable HTTP benchmark harness for
  the major UI-backed northbound routes.
- Changed `/Client` and `/Identities` to rely on the inbound worker's cached
  announce import instead of doing a blocking `reticulumd list_announces` on
  every UI request.
- Kept synchronous announce refresh on broadcast routing, where it affects
  delivery decisions rather than operator UI reads.
- Added targeted SQLite reads for identity announces, identity states,
  identity REM modes, and file attachments.
- Added read-only command handling for R3AKT list/get style commands so they do
  not rewrite the full SQLite snapshot.
- Added read-only command handling for checklist template list/get commands.
- Added a R3AKT-specific SQLite read snapshot that excludes unrelated large
  tables such as messages, telemetry, system events, attachments, and command
  result caches from read-only mission registry commands.
- Added direct checklist template list loading over template and column tables.
- Added bounded audit-event loading for `/api/r3akt/events`.
- Moved `/api/r3akt/snapshots` to the same R3AKT-specific read snapshot used
  by mission registry reads.
- Split dashboard `/Status` runtime reporting from full diagnostics so the UI
  polling path no longer performs receipt polling, persistence diagnostics, or
  full service inventory assembly on every status read.
- Added a summary mode for `/api/r3akt/events` so UI workspace loading can
  avoid serializing large checklist/template payload snapshots when only the
  event timeline metadata is needed.
- Added targeted SQLite read models for R3AKT missions, mission changes, log
  entries, teams, team members, assets, assignments, and EAM list reads.
- Added `include_delta=false` for mission changes and moved the UI endpoint to
  that lighter shape while preserving full-delta API output by default.
- Added read-only SQLite opening for pure read paths so benchmarked read routes
  skip migration setup and avoid write-capable connection overhead.
- Added a 50-member HTTP topic fanout regression test to cover the Python
  failure mode where propagation/fanout became unreliable past a small number
  of members.
- Corrected the speed-test telemetry route to call `/Telemetry?since=0`, so
  telemetry is now measured instead of counted as a harness failure.

## Remaining Slow Surfaces

The generic `/Events` stream still returns a large payload, about 748 KB in the
current live dataset. It now averages ~40 ms in the short run after the rebuild,
but should still get pagination before much larger deployments.

The full-payload `/api/r3akt/events` compatibility call still returns 5.4 MB
for the current manual history dataset. That is acceptable as an explicit API
request, but should not be used by default UI workspace loading. The UI-backed
summary call now averages ~16 ms.

`/api/r3akt/snapshots` still returns a full state snapshot and remains slower
than Python's empty-store baseline. It is primarily an export/diagnostic route,
not a high-frequency workspace load route.

Most normal operator routes are now under 100 ms in the short live benchmark,
with most high-frequency UI reads under 40 ms.

After the read-only SQLite fast path, most high-frequency UI reads on the
manual dataset are below 6 ms, including status, clients, identities, REM
peers, topics, subscribers, files, images, EAM, and the common R3AKT list
routes. The slower remaining surfaces are large payload or diagnostic/export
routes rather than LXMF-rs dispatch overhead.

## Verification

Passed:

- `cargo test -p r3akt-rch-server client_records_ -- --test-threads=1`
- `cargo test -p r3akt-rch-server rem_peer_registry_route -- --test-threads=1`
- `cargo test -p r3akt-rch-server checklist_template -- --test-threads=1`
- `cargo test -p r3akt-rch-server file_and_image_routes -- --test-threads=1`
- `cargo test -p r3akt-rch-server r3akt_mission -- --test-threads=1`
- `cargo test -p r3akt-rch-server r3akt_mission_change_and_log_routes_persist_with_python_shapes -- --test-threads=1`
- `cargo test -p r3akt-rch-core sqlite_snapshot_restores_topics_subscribers_messages_and_command_cache -- --test-threads=1`
- `cargo test -p r3akt-rch-server status_route_matches_python_dashboard_snapshot_shape -- --test-threads=1`
- `cargo test -p r3akt-rch-server runtime_diagnostics_routes_report_rust_runtime_state -- --test-threads=1`
- `cargo test -p r3akt-rch-server chat_topic_send_fans_out_to_fifty_members_reliably -- --test-threads=1`
- `cargo test -p r3akt-rch-server chat_topic_send_fans_out_through_reticulumd_rpc_subscribers -- --test-threads=1`
- `cargo test -p r3akt-rch-server broadcast_dispatch_does_not_sleep_between_hundred_recipients -- --test-threads=1`
- `cargo test -p r3akt-rch-server broadcast_destination_routing_loads_snapshot_once_for_many_clients -- --test-threads=1`
- `cargo fmt --all -- --check`
- `cargo clippy -p r3akt-rch-server --all-targets -- -D warnings`
- `cargo build --release -p r3akt-rch-server`
