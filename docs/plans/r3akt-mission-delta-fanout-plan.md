# R3AKT Mission Delta Fanout Plan (Reviewed and Improved)

## Review Outcome
The previous plan was directionally correct but had four gaps that would cause implementation drift:
1. Announce capability payload position was off by one. In this codebase it is the third announce list item (`index 2`), not list element `3` in zero-based indexing terms.
2. Additive DB migration was not concrete. `Base.metadata.create_all()` does not add new columns on existing tables, so an explicit `ALTER TABLE` migration path is required.
3. REST and LXMF currently use different `MissionDomainService` instances in gateway mode. Without shared service wiring, mission-change fanout listeners cannot cover both paths.
4. Duplicate fanout control was stated but not operationally defined.

This plan supersedes the prior version and is implementation-ready.

## Goal
Emit mission updates as compact, per-mutation deltas for logs, assets, and tasks; persist each delta as a mission change; then fan out to mission recipients with capability-aware LXMF formatting.

## Contract Review Findings (Plan Validation)
1. The plan is strong on backend behavior, but the client-facing contract needs stronger normative language for future R3AKT clients.
2. The AsyncAPI currently emphasizes command/reply/event fields and does not yet fully define the `FIELD_CUSTOM_TYPE/ DATA/ META` payload contract used for R3AKT delta fanout.
3. The contract must explicitly define identity keys (`mission_uid` vs `mission_id`) and idempotency keys (`mission_change.uid`) to prevent client-side ambiguity.
4. The source-of-truth AsyncAPI path for this work is:
   1. `C:/Users/broth/Documents/work/ATAK/src/R3AKT/R3AKT/docs/architecture/asyncapi/r3akt-mission-sync-lxmf.asyncapi.yaml`
5. Repository-local AsyncAPI should remain aligned:
   1. `docs/architecture/asyncapi/r3akt-mission-sync-lxmf.asyncapi.yaml`

## Scope
In:
1. Delta persistence on mission changes for logs/assets/tasks.
2. Automatic fanout to mission team-member identities and linked clients.
3. Capability-aware transport behavior (`R3AKT` custom fields vs markdown body fallback).
4. OpenAPI and AsyncAPI contract updates.
5. Additive migration for existing databases.

Out:
1. Full mission-tree snapshot sync.
2. New transport protocols beyond LXMF.
3. New mission/change enums beyond existing `MissionChangeType`.

## Locked Decisions
1. Delta model is per-event and mutation-scoped.
2. Delta scope is logs/assets/tasks only.
3. Change persistence is automatic for qualifying mutations.
4. Wire identifier remains `r3akt.mission.change.v1`.
5. Non-R3AKT recipients receive markdown body updates.
6. Broadcast button remains manual and additive.
7. `mission_uid` is canonical across REST, domain, and AsyncAPI; `mission_id` is alias-only during transition.

## Normative Client Contract (Must Be Implementable)
### Transport Profiles
1. `profile=r3akt`:
   1. Clients consume mission delta from LXMF custom fields.
   2. `FIELD_CUSTOM_TYPE (0xFB)` must equal `r3akt.mission.change.v1`.
   3. `FIELD_CUSTOM_DATA (0xFC)` must contain `mission_uid`, `mission_change`, `delta`.
   4. `FIELD_CUSTOM_META (0xFD)` must contain `version`, `event_type`, `mission_uid`, `encoding`, `source`.
2. `profile=generic_lxmf`:
   1. Clients consume human-readable markdown message body.
   2. Custom R3AKT fields may be absent.

### Ordering and Idempotency
1. `mission_change.uid` is the idempotency key.
2. Clients must de-duplicate by `mission_change.uid`.
3. `timestamp` and `emitted_at` are RFC3339/ISO-8601 UTC datetimes.
4. Delivery is at-least-once; duplicates are expected and must be safe.

### Compatibility Rules
1. New fields are additive and optional unless marked required in schema.
2. Unknown `delta.tasks[].op` values must be ignored safely (forward compatibility).
3. Clients that only understand markdown remain functional.

## Target Data Contract
### Mission Change Record
Persist an additive JSON column on `r3akt_mission_changes`:
1. SQLAlchemy field: `delta_json = Column("delta", JSON, nullable=True)`.
2. Domain/API shape: exposed as `delta`.

### Delta Envelope
Use one envelope shape for storage and fanout payload:
1. `version`: integer (`1`).
2. `source_event_type`: string.
3. `emitted_at`: ISO datetime.
4. `logs`: list.
5. `assets`: list.
6. `tasks`: list.
7. `contract_version`: string (`r3akt.mission.change.v1`) for wire/document parity.

### Delta Item Shapes
1. `logs[]`: `op=upsert`, `entry_uid`, `mission_uid`, `content`, `server_time`, `client_time`, `keywords`, `content_hashes`.
2. `assets[]`: `op=upsert|delete`, `asset_uid`, `team_member_uid`, `name`, `asset_type`, `status`, `location`, `notes`.
3. `tasks[]`: `op=status_set|row_added|row_deleted|row_style_set|cell_set|assignment_upsert|assignment_assets_set|assignment_asset_linked|assignment_asset_unlinked`, with mission/checklist/task/assignment identifiers and operation-specific fields.

### Mission Change Type Mapping
1. Upsert/set/add/link operations map to `ADD_CONTENT`.
2. Delete/unlink operations map to `REMOVE_CONTENT`.

## Mutation-to-Delta Mapping
### Logs
1. `upsert_log_entry` -> `delta.logs[0].op=upsert`.

### Assets
1. `upsert_asset` -> `delta.assets[0].op=upsert`.
2. `delete_asset` -> `delta.assets[0].op=delete`.

### Tasks and Assignments
1. `upsert_assignment` -> `delta.tasks[0].op=assignment_upsert`.
2. `set_assignment_assets` -> `delta.tasks[0].op=assignment_assets_set`.
3. `link_assignment_asset` -> `delta.tasks[0].op=assignment_asset_linked`.
4. `unlink_assignment_asset` -> `delta.tasks[0].op=assignment_asset_unlinked`.
5. `set_checklist_task_status` -> `delta.tasks[0].op=status_set`.
6. `add_checklist_task_row` -> `delta.tasks[0].op=row_added`.
7. `delete_checklist_task_row` -> `delta.tasks[0].op=row_deleted`.
8. `set_checklist_task_row_style` -> `delta.tasks[0].op=row_style_set`.
9. `set_checklist_task_cell` -> `delta.tasks[0].op=cell_set`.

Checklist methods must resolve `mission_uid` from checklist. If checklist is not mission-linked (`mission_uid` is null), skip mission-change emission.

## Fanout and Recipient Rules
1. Trigger fanout from mission-change creation, not from ad hoc command reply inspection.
2. Recipient set comes from `MissionDomainService.list_mission_team_member_identities(mission_uid)`.
3. Recipients include both member `rns_identity` and linked `client_identities`, deduplicated.
4. One fanout cycle per mission change UID.
5. No duplicate fanout for a single mutation.

## Capability Detection Rules
1. Parse capabilities from announce app-data list third element (`index 2`).
2. Decode payload with tolerant strategy:
   1. Try CBOR first.
   2. Fallback to msgpack.
3. Normalize capabilities case-insensitively.
4. Canonical match token: `r3akt`.
5. Cache capabilities per identity with TTL (default 6 hours).
6. On cache miss/stale, fallback to persisted grants via `api.list_identity_capabilities(identity)`.

## LXMF Transport Behavior
### R3AKT-Capable Recipients
1. Send concise body plus custom fields:
   1. `FIELD_CUSTOM_TYPE (0xFB) = "r3akt.mission.change.v1"`.
   2. `FIELD_CUSTOM_DATA (0xFC)` includes `mission_uid`, `mission_change`, `delta`.
   3. `FIELD_CUSTOM_META (0xFD)` includes `version`, `event_type`, `mission_uid`, `encoding`, `source`.

### Non-R3AKT Recipients
1. Send markdown mission-update body with concise delta summary.
2. Keep standard event field for traceability.
3. Do not include R3AKT custom fields.

## File-by-File Implementation Plan
1. `reticulum_telemetry_hub/api/storage_models.py`
   1. Add mission-change `delta` JSON column mapping.
2. `reticulum_telemetry_hub/mission_domain/models.py`
   1. Add optional `delta` to `MissionChange`.
3. `reticulum_telemetry_hub/mission_domain/service.py`
   1. Serialize/deserialize `delta` on mission-change records.
   2. Add explicit additive migration helper for `r3akt_mission_changes.delta`.
   3. Add internal helper to auto-create mission changes with generated deltas.
   4. Hook helper into all qualifying mutation methods listed above.
   5. Add mission-change listener registration API and emit notifications post-commit.
4. `reticulum_telemetry_hub/reticulum_server/announce_capabilities.py`
   1. Add decode helper for inbound capability payload parsing.
5. `reticulum_telemetry_hub/reticulum_server/__main__.py`
   1. Extend announce handling to ingest capabilities and update TTL cache.
   2. Register mission-change listener on hub `mission_domain_service`.
   3. Implement capability-aware formatter/sender for mission-change fanout.
   4. Gate or remove legacy `_fanout_mission_team_events` paths for delta-managed events to prevent duplicate outbound messages.
6. `reticulum_telemetry_hub/northbound/gateway.py`
   1. Pass `hub.mission_domain_service` into `create_app(...)` so REST and LXMF mutations share one domain service and one fanout listener.
7. `reticulum_telemetry_hub/northbound/app.py`
   1. Ensure provided `mission_domain_service` is used directly and not re-created.
8. `API/ReticulumCommunityHub-OAS.yaml`
   1. Add `delta` field to `R3aktMissionChange`.
   2. Update `R3aktMissionChangeUpsertRequest` examples/schema notes for optional `delta`.
9. `docs/architecture/contract-mapping.md`
   1. Document capability-aware dual-path transport and field semantics.
10. `C:/Users/broth/Documents/work/ATAK/src/R3AKT/R3AKT/docs/architecture/asyncapi/r3akt-mission-sync-lxmf.asyncapi.yaml`
   1. Add explicit custom-field contract section for `0xFB/0xFC/0xFD`.
   2. Add `MissionDeltaEvent` schema including `mission_change` and `delta`.
   3. Define required/optional fields and idempotency expectations.
   4. Normalize identifiers to `mission_uid` (with transitional alias guidance).
11. `docs/architecture/asyncapi/r3akt-mission-sync-lxmf.asyncapi.yaml`
   1. Mirror the same contract updates to keep local docs aligned.

## Tests and Validation
1. `tests/mission_domain/test_service.py`
   1. Verify each qualifying mutation creates exactly one mission change with expected delta payload.
   2. Verify checklist mutations without mission link do not emit mission changes.
2. `tests/api/test_r3akt_migrations.py`
   1. Verify additive migration adds `delta` column to legacy DB without data loss.
3. `tests/test_announce_handler.py`
   1. Verify capability extraction from announce app-data index `2`.
4. `tests/test_reticulum_server_daemon.py`
   1. Verify R3AKT recipients receive custom fields.
   2. Verify non-R3AKT recipients receive markdown body and no custom fields.
   3. Verify no duplicate outbound messages per mutation.
5. `tests/northbound/test_gateway_runtime.py`
   1. Verify gateway app uses hub-provided mission domain service instance.
6. `tests/northbound/test_openapi_r3akt_paths.py`
   1. Verify mission-change schemas include `delta`.
7. Contract lint/consistency checks:
   1. Validate AsyncAPI schema parses cleanly after `MissionDeltaEvent` additions.
   2. Verify OAS and AsyncAPI use consistent canonical field names (`mission_uid`, `change_type`, `delta`).
   3. Verify custom-field constants are documented and match runtime (`0xFB/0xFC/0xFD`).
8. Regression checks:
   1. `ruff check .`
   2. Targeted pytest modules above.
   3. Full `pytest` pass if time allows.

## Risks and Mitigations
1. Risk: Duplicate fanout from legacy and new pathways.
   1. Mitigation: enforce one authoritative fanout trigger (mission-change listener) and skip legacy for managed event set.
2. Risk: Capability cache staleness.
   1. Mitigation: TTL plus grants fallback.
3. Risk: Migration not applied on existing DB.
   1. Mitigation: explicit `PRAGMA table_info` + `ALTER TABLE` startup migration.
4. Risk: Oversized human-readable payloads.
   1. Mitigation: concise markdown templates with clipped lists.

## Acceptance Criteria
1. No full mission tree is sent for logs/assets/tasks updates.
2. Every qualifying mutation writes one mission change with structured `delta`.
3. Mission recipients equal team-member identities plus linked clients.
4. R3AKT-capable recipients get update payload in custom fields.
5. Non-R3AKT recipients get readable mission update in message body.
6. Each mutation emits one fanout cycle without duplicates.
7. OAS, AsyncAPI, and implementation remain aligned.
8. A new R3AKT client can implement delta ingestion using only published contract artifacts (no code inspection required).
