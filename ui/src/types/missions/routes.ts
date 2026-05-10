export const MISSION_SELECTION_STORAGE_KEY = "rth-ui-missions-selected-mission-uid";

export const MISSION_DOMAIN_ROUTE_NAMES = {
  root: "mission-domain-root",
  overview: "mission-domain-overview",
  mission: "mission-domain-mission",
  topic: "mission-domain-topic",
  checklist: "mission-domain-checklists",
  checklistTask: "mission-domain-checklist-tasks",
  checklistTemplate: "mission-domain-checklist-templates",
  team: "mission-domain-teams",
  teamMember: "mission-domain-team-members",
  skill: "mission-domain-skills",
  teamMemberSkill: "mission-domain-team-member-skills",
  taskSkillRequirement: "mission-domain-task-skill-requirements",
  asset: "mission-domain-assets",
  assignment: "mission-domain-assignments",
  zone: "mission-domain-zones",
  domainEvent: "mission-domain-events",
  missionChange: "mission-domain-mission-changes",
  logEntry: "mission-domain-log-entries",
  snapshot: "mission-domain-snapshots",
  auditEvent: "mission-domain-audit-events"
} as const;

export type MissionDomainRouteName =
  (typeof MISSION_DOMAIN_ROUTE_NAMES)[keyof typeof MISSION_DOMAIN_ROUTE_NAMES];

export const missionDomainPath = (missionUid: string, segment: string): string =>
  `/missions/${encodeURIComponent(missionUid)}/${segment}`;

export const toMissionUidFromRouteParam = (value: unknown): string => {
  if (Array.isArray(value)) {
    return String(value[0] ?? "").trim();
  }
  return String(value ?? "").trim();
};
