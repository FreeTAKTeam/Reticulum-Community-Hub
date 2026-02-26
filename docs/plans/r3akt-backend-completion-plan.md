# R3AKT Domain Completion Plan (Diagram-Parity, Execution-Ready)

## Goal
Finish the R3AKT backend so `docs/architecture/R3AKT_Domain_Class_Diagram.mmd` is fully implemented in code and operationally exposed through:
- Reticulum southbound command handling.
- Northbound HTTP APIs.

This plan is implementation-first: each phase has concrete outputs, file targets, and exit gates.

## Scope
### In
- All domain classes, enums, associations, and invariants in the R3AKT diagram.
- Domain persistence and service behavior in this repository.
- Southbound command exposure for completed domain operations.
- Northbound route and OpenAPI completion for completed domain operations.

### Out
- Non-R3AKT domains (analytics/gateway/agent-runtime that are not in the class diagram).
- UI feature work not required to validate backend completion.

## What changed in this improved plan
- Added full traceability checklist across classes, enums, and associations.
- Locked previously open decisions to prevent implementation stalls.
- Added phase gates tied to tests and compatibility outcomes.
- Added explicit migration/backfill and rollback boundaries.

## Locked decisions (to unblock execution)
1. `MissionRde` implementation:
   - Implement as first-class table `r3akt_mission_rde` with `mission_uid` (unique) and `role` enum.
   - Do not map this indirectly to capability grants.
2. `Mission.Topic` response shape:
   - Default response keeps `topic_id`.
   - Optional expansion (`expand=topic`) returns embedded topic object.
3. Assignment assets migration:
   - Dual-write for one release cycle (`assets_json` + normalized link table).
   - Dual-read during migration; remove JSON write in follow-up cleanup phase.

## Diagram parity baseline

### Class coverage status
| Diagram class | Current status | Required completion |
|---|---|---|
| `Mission` | Partial | Complete field parity + relation operations |
| `MissionChange` | Partial | Enforce enum + full normalization |
| `LogEntry` | Partial | Keep marker linkage validation + mission-scoped querying |
| `Team` | Partial | Enforce `TeamColor` enum |
| `TeamMember` | Partial | Expose all member attributes + role enum validation |
| `Asset` | Partial | Keep status enum + normalized assignment links |
| `Skill` | Partial | Add stricter validation and lifecycle completeness |
| `TeamMemberSkill` | Partial | Level bounds + expiry validation |
| `TaskSkillRequirement` | Partial | Bounds/mandatory enforcement |
| `Checklist` | Mostly complete | Add `UPLOAD_PENDING` + strict enum enforcement |
| `ChecklistTask` | Mostly complete | Validate all status transitions against enums/invariants |
| `ChecklistColumn` | Mostly complete | Ensure type/system key enums enforced |
| `ChecklistCell` | Mostly complete | Preserve relation integrity under row/column operations |
| `ChecklistTemplate` | Mostly complete | Keep lineage semantics (`sourceTemplateUid`) |
| `ChecklistFeedPublication` | Mostly complete | Maintain offline/sync invariant |
| `MissionTaskAssignment` | Partial | Normalize assets relation + status enum enforcement |
| `Zone` / `ZonePoint` | Implemented separately | Add explicit mission association |
| `Topic` | Implemented separately | Add explicit mission-topic resolution path |
| `Client` | Implemented separately | Add explicit TeamMember linkage |
| `MissionRde` | Missing | Add model/persistence/service/routes |

### Enum coverage status
All diagram enums move to centralized strict validation (no permissive free-form strings) via a shared enum module.

Target enums:
- `missionRoleList`, `missionStatus`, `MissionChangeType`
- `TeamRole`, `TeamColor`
- `checklistStatus`, `checklistTaskStatus`, `checklistUserTaskStatus`
- `checklistMode`, `checklistSyncState`, `checklistOriginType`
- `checklistColumnType`, `checklistSystemColumnKey`
- `AssetStatus`

### Association coverage status
| Association | Current state | Required completion |
|---|---|---|
| Mission parent/children | Field exists | Add cycle-safe operations + query surfaces |
| Mission -> MissionChange | Implemented | Enforce enum and consistency |
| Mission -> LogEntry | Implemented | Enforce mission integrity |
| Mission -> Team | Implemented | Enforce minimum and relation checks at service level |
| Mission -> Zone | Missing explicit link | Add `r3akt_mission_zone_links` |
| Mission -> Topic | Implicit id only | Add expansion + validation |
| Team -> TeamMember | Implemented | Add full member fields + role validation |
| TeamMember -> Client | Missing explicit link | Add `r3akt_team_member_client_links` |
| TeamMember -> Asset | Implemented | Keep consistency checks |
| Checklist -> Tasks/Columns/FeedPublications | Implemented | Keep invariants strict |
| Task -> Skill requirements | Implemented | Add level bound checks |
| Assignment <-> Asset | JSON list only | Add `r3akt_assignment_assets` normalized table |
| Skill -> member/task requirements | Implemented | Keep integrity validation |

## Implementation workstreams

### Workstream A: Canonical enums and validators
Files:
- `reticulum_telemetry_hub/mission_domain/enums.py` (new)
- `reticulum_telemetry_hub/mission_domain/service.py`
- `reticulum_telemetry_hub/northbound/routes_r3akt.py`
- `reticulum_telemetry_hub/northbound/routes_checklists.py`
- `reticulum_telemetry_hub/mission_sync/router.py`
- `reticulum_telemetry_hub/checklist_sync/router.py`

Deliverables:
- Single source of truth for domain enums.
- Validation helpers used by all mutating operations.

### Workstream B: Persistence normalization for missing associations
Files:
- `reticulum_telemetry_hub/api/storage_models.py`
- `reticulum_telemetry_hub/mission_domain/service.py`
- `tests/api/test_r3akt_migrations.py`

Deliverables:
- Additive tables:
  - `r3akt_mission_zone_links`
  - `r3akt_team_member_client_links`
  - `r3akt_assignment_assets`
  - `r3akt_mission_rde`
- Backfill and dual-write/dual-read support for assignment assets.

### Workstream C: Mission aggregate completion
Files:
- `reticulum_telemetry_hub/mission_domain/service.py`
- `reticulum_telemetry_hub/mission_domain/models.py`
- `reticulum_telemetry_hub/northbound/routes_r3akt.py`

Deliverables:
- Full mission field handling (`path`, `classification`, `tool`, `keywords`, `parent`, `feeds`, `password_hash`, `mission_priority`, `token`, `expiration`).
- Parent/child management operations with cycle detection.
- Mission-zone link operations.
- Optional mission-topic expansion.
- MissionRde CRUD/read.

### Workstream D: Team/member/client completion
Files:
- `reticulum_telemetry_hub/mission_domain/service.py`
- `reticulum_telemetry_hub/northbound/routes_r3akt.py`

Deliverables:
- Team color and member role enum validation.
- Full TeamMember attribute lifecycle (`icon`, `freq`, `email`, `phone`, `modulation`, `availability`, `certifications`, `last_active`).
- TeamMember-client link/unlink/query operations.

### Workstream E: Checklist and assignment final alignment
Files:
- `reticulum_telemetry_hub/mission_domain/service.py`
- `reticulum_telemetry_hub/checklist_sync/router.py`
- `reticulum_telemetry_hub/northbound/routes_checklists.py`

Deliverables:
- Support `UPLOAD_PENDING` state and transitions.
- Strict checklist enum enforcement.
- Assignment status validation against checklist task status enum.
- Normalized assignment-asset relations with compatibility reads.

### Workstream F: Southbound exposure completion
Files:
- `reticulum_telemetry_hub/mission_sync/capabilities.py`
- `reticulum_telemetry_hub/checklist_sync/capabilities.py`
- `reticulum_telemetry_hub/mission_sync/router.py`
- `reticulum_telemetry_hub/checklist_sync/router.py`

Deliverables:
- Add command handlers and capability gates for newly completed domain operations.
- Emit command result and event envelopes for all mutating actions.

### Workstream G: Northbound API and contract completion
Files:
- `reticulum_telemetry_hub/northbound/routes_r3akt.py`
- `API/ReticulumCommunityHub-OAS.yaml`
- `tests/northbound/test_openapi_r3akt_paths.py`
- `tests/northbound/test_routes_rest_extended.py`

Deliverables:
- Add missing lifecycle/association endpoints.
- Keep backward compatibility on existing payload shapes.
- OpenAPI parity with implemented routes.

### Workstream H: Auditability, traceability, and docs
Files:
- `tests/mission_domain/test_diagram_parity.py` (new)
- `docs/dataArchitecture.md`
- `docs/architecture/contract-mapping.md`

Deliverables:
- Diagram-to-code parity test.
- Updated architecture/docs with final domain mapping.

## Phase plan and exit gates

### Phase 1: Enums + schema normalization
Exit gates:
- New tables created idempotently.
- Enum validation wired in service paths.
- Existing tests remain green.

### Phase 2: Mission/team/member/client parity
Exit gates:
- Mission and TeamMember full field coverage implemented.
- Mission parent/zone/topic and TeamMember-client associations working.
- New service + northbound tests pass.

### Phase 3: Checklist/assignment alignment
Exit gates:
- `UPLOAD_PENDING` behavior validated.
- Assignment assets normalized and compatibility reads validated.
- Checklist invariant tests pass.

### Phase 4: Southbound + northbound completion
Exit gates:
- New domain operations callable via Reticulum commands.
- New/updated HTTP routes documented in OpenAPI and tested.
- Capability matrix updated and enforced.

### Phase 5: Hardening and closure
Exit gates:
- Diagram parity test passes.
- Migration/backfill tests pass on legacy + new DB states.
- Docs updated to reflect final architecture.

## Test plan
### Service/domain tests
- Extend `tests/mission_domain/test_service.py` for:
  - full mission fields
  - MissionRde
  - mission-zone links
  - parent cycle detection
  - member-client links
  - assignment-asset normalization
  - enum rejection cases

### Router/contract tests
- Extend `tests/mission_sync/test_mission_router.py` and `tests/checklist_sync/test_checklist_router.py` for new command operations.
- Extend `tests/northbound/test_routes_rest_extended.py` for new endpoints and error semantics.
- Extend `tests/northbound/test_openapi_r3akt_paths.py` for path coverage.

### Migration tests
- Extend `tests/api/test_r3akt_migrations.py` for new tables and additive behavior.
- Add migration regression tests for `assets_json` backfill to `r3akt_assignment_assets`.

### Parity tests
- Add `tests/mission_domain/test_diagram_parity.py` to assert all diagram entities/enums/associations are represented.

## Compatibility and rollout
1. Apply additive migrations and backfill.
2. Enable dual-write/dual-read for assignment assets.
3. Release with compatibility mode for one cycle.
4. Remove legacy JSON write path in cleanup release after verification.

## Rollback plan
- Rollback boundary is code path only; no destructive schema rollback.
- On rollback, keep additive tables intact and disable new handlers/routes.
- Preserve legacy read/write behavior for assignment assets during rollback window.

## Final acceptance checklist
- [x] All diagram classes are represented and test-covered.
- [x] All diagram enums are strict-validated across southbound and northbound.
- [x] All diagram associations are enforceable and queryable.
- [x] All documented invariants are enforced by service logic and tests.
- [x] Southbound commands support completed domain operations.
- [x] Northbound routes and OpenAPI fully describe completed domain operations.
- [x] Migration and compatibility tests pass on both fresh and existing databases.
