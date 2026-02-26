# Missions Domain-Object Split Plan (Implementation Tracker)

## Goal
Split mission workspace concepts into canonical mission-domain pages while preserving existing route/API behavior and mission selection persistence.

## Canonical Route Pattern
- `/missions/:mission_uid/overview`
- `/missions/:mission_uid/mission`
- `/missions/:mission_uid/topic`
- `/missions/:mission_uid/checklists`
- `/missions/:mission_uid/checklist-tasks`
- `/missions/:mission_uid/checklist-templates`
- `/missions/:mission_uid/teams`
- `/missions/:mission_uid/team-members`
- `/missions/:mission_uid/skills`
- `/missions/:mission_uid/team-member-skills`
- `/missions/:mission_uid/task-skill-requirements`
- `/missions/:mission_uid/assets`
- `/missions/:mission_uid/assignments`
- `/missions/:mission_uid/zones`
- `/missions/:mission_uid/domain-events`
- `/missions/:mission_uid/mission-changes`
- `/missions/:mission_uid/log-entries`
- `/missions/:mission_uid/snapshots`
- `/missions/:mission_uid/audit-events`

## Wave Status

### Wave 1 - Shell and Route Skeleton
Status: Completed
- Added mission domain route constants under `ui/src/types/missions/routes.ts`.
- Added mission workspace shell `ui/src/pages/missions/MissionsWorkspacePage.vue`.
- Added nested mission-domain routes in `ui/src/router/index.ts`.
- Added mission scope synchronization composable `ui/src/composables/missions/useMissionScope.ts`.
- Added shared workspace store `ui/src/stores/missionWorkspace.ts`.

### Wave 2 - Mission, Topic, Overview
Status: Completed (read-first)
- Added `MissionOverviewPage.vue`, `MissionObjectPage.vue`, `TopicObjectPage.vue`.
- Added reusable domain record scaffold component.

### Wave 3 - Checklist Domains
Status: Completed (read-first)
- Added `ChecklistObjectPage.vue`, `ChecklistTaskObjectPage.vue`, `ChecklistTemplateObjectPage.vue`.

### Wave 4 - Team/Member/Skill Domains
Status: Completed (read-first)
- Added `TeamObjectPage.vue`, `TeamMemberObjectPage.vue`, `SkillObjectPage.vue`, `TeamMemberSkillObjectPage.vue`, `TaskSkillRequirementObjectPage.vue`.

### Wave 5 - Asset/Assignment Domains
Status: Completed
- Added canonical `AssetObjectPage.vue` and `AssignmentObjectPage.vue`.
- Added compatibility wrapper route behavior for `MissionAssetsPage.vue`.

### Wave 6 - Zones + Logs/Events/Changes/Snapshots/Audit
Status: Completed
- Added `ZoneObjectPage.vue`, `DomainEventObjectPage.vue`, `MissionChangeObjectPage.vue`, `LogEntryObjectPage.vue`, `SnapshotObjectPage.vue`, `AuditEventObjectPage.vue`.
- Added compatibility wrapper route behavior for `MissionLogsPage.vue`.

### Wave 7 - Hardening
Status: In progress
- `MissionsPage.vue` cut over to thin redirect container.
- Monolith moved to `ui/src/pages/missions/MissionsLegacyPage.vue` and exposed at `/missions/legacy`.
- Pending full parity extraction of all write flows from legacy page into dedicated domain pages/composables.
- Pending expanded automated tests for action parity snapshots.
- Pending full manual QA sign-off across all new mission-domain routes.

## Functional Preservation Invariants
- Endpoint contracts remain unchanged (`ui/src/api/endpoints.ts`).
- Legacy entry points `/missions`, `/missions/assets`, `/missions/logs`, `/checklists` remain accessible.
- Mission selection persistence key remains `rth-ui-missions-selected-mission-uid`.
- Query parameter `mission_uid` remains synchronized where applicable.

## QA Gate
After each extension wave, run:
1. `cd ui && npm run lint`
2. `cd ui && npm run test -- --run`
3. `cd ui && npm run build`
4. Manual browser checks using `docs/CosmicUiManualQa.md`
