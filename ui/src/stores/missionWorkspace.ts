import { computed } from "vue";
import { ref } from "vue";
import { defineStore } from "pinia";
import type { RouteLocationNormalizedLoaded } from "vue-router";
import type { Router } from "vue-router";
import { get } from "../api/client";
import { endpoints } from "../api/endpoints";
import { loadJson } from "../utils/storage";
import { saveJson } from "../utils/storage";
import type {
  AssetRaw,
  AssignmentRaw,
  ChecklistRaw,
  DomainEventRaw,
  LogEntryRaw,
  MissionChangeRaw,
  MissionRaw,
  SkillRaw,
  TaskSkillRequirementRaw,
  TeamMemberRaw,
  TeamMemberSkillRaw,
  TeamRaw,
  TemplateRaw,
  TopicRaw,
  ZoneRaw
} from "../types/missions/raw";
import { MISSION_SELECTION_STORAGE_KEY } from "../types/missions/routes";

const toArray = <T>(value: unknown): T[] => (Array.isArray(value) ? (value as T[]) : []);

const toText = (value: unknown): string => {
  if (Array.isArray(value)) {
    return String(value[0] ?? "").trim();
  }
  return String(value ?? "").trim();
};

const missionUidFromChecklist = (entry: ChecklistRaw): string =>
  String(entry.mission_uid ?? entry.mission_id ?? "").trim();

export type MissionWorkspaceCollectionKey =
  | "missions"
  | "topics"
  | "checklists"
  | "templates"
  | "teams"
  | "members"
  | "assets"
  | "assignments"
  | "events"
  | "missionChanges"
  | "logEntries"
  | "zones"
  | "skills"
  | "teamMemberSkills"
  | "taskSkillRequirements";

export const useMissionWorkspaceStore = defineStore("mission-workspace", () => {
  const missions = ref<MissionRaw[]>([]);
  const topics = ref<TopicRaw[]>([]);
  const checklists = ref<ChecklistRaw[]>([]);
  const templates = ref<TemplateRaw[]>([]);
  const teams = ref<TeamRaw[]>([]);
  const members = ref<TeamMemberRaw[]>([]);
  const assets = ref<AssetRaw[]>([]);
  const assignments = ref<AssignmentRaw[]>([]);
  const events = ref<DomainEventRaw[]>([]);
  const missionChanges = ref<MissionChangeRaw[]>([]);
  const logEntries = ref<LogEntryRaw[]>([]);
  const zones = ref<ZoneRaw[]>([]);
  const skills = ref<SkillRaw[]>([]);
  const teamMemberSkills = ref<TeamMemberSkillRaw[]>([]);
  const taskSkillRequirements = ref<TaskSkillRequirementRaw[]>([]);

  const loading = ref(false);
  const error = ref("");
  const selectedMissionUid = ref("");
  const lastLoadedAt = ref("");

  const selectedMission = computed(() => {
    const missionUid = selectedMissionUid.value;
    return missions.value.find((entry) => String(entry.uid ?? "").trim() === missionUid);
  });

  const missionSelectOptions = computed(() => {
    return missions.value
      .map((entry) => {
        const uid = String(entry.uid ?? "").trim();
        if (!uid) {
          return null;
        }
        const missionName = String(entry.mission_name ?? uid).trim() || uid;
        const status = String(entry.mission_status ?? "UNSCOPED").trim();
        return {
          value: uid,
          label: `${missionName} (${status || "UNKNOWN"})`
        };
      })
      .filter((entry): entry is { value: string; label: string } => entry !== null)
      .sort((left, right) => left.label.localeCompare(right.label));
  });

  const missionScopedChecklists = computed(() => {
    const missionUid = selectedMissionUid.value;
    if (!missionUid) {
      return [] as ChecklistRaw[];
    }
    return checklists.value.filter((entry) => missionUidFromChecklist(entry) === missionUid);
  });

  const missionScopedTeamUids = computed(() => {
    const missionUid = selectedMissionUid.value;
    if (!missionUid) {
      return new Set<string>();
    }
    const next = new Set<string>();
    teams.value.forEach((entry) => {
      const teamUid = String(entry.uid ?? "").trim();
      if (!teamUid) {
        return;
      }
      const missionUids = new Set([
        ...toArray<string>(entry.mission_uids).map((item) => String(item ?? "").trim()),
        String(entry.mission_uid ?? "").trim()
      ]);
      if (missionUids.has(missionUid)) {
        next.add(teamUid);
      }
    });
    return next;
  });

  const missionScopedMembers = computed(() => {
    const teamUids = missionScopedTeamUids.value;
    return members.value.filter((entry) => teamUids.has(String(entry.team_uid ?? "").trim()));
  });

  const missionScopedMemberUids = computed(() => {
    const next = new Set<string>();
    missionScopedMembers.value.forEach((entry) => {
      const uid = String(entry.uid ?? "").trim();
      if (uid) {
        next.add(uid);
      }
    });
    return next;
  });

  const missionScopedAssets = computed(() => {
    const missionUid = selectedMissionUid.value;
    if (!missionUid) {
      return [] as AssetRaw[];
    }
    const memberUids = missionScopedMemberUids.value;
    const assignmentAssetUids = new Set<string>();
    assignments.value
      .filter((entry) => String(entry.mission_uid ?? "").trim() === missionUid)
      .forEach((entry) => {
        toArray<string>(entry.assets)
          .map((item) => String(item ?? "").trim())
          .filter((item) => item.length > 0)
          .forEach((item) => assignmentAssetUids.add(item));
      });

    return assets.value.filter((entry) => {
      const assetUid = String(entry.asset_uid ?? "").trim();
      if (!assetUid) {
        return false;
      }
      const memberUid = String(entry.team_member_uid ?? "").trim();
      return memberUids.has(memberUid) || assignmentAssetUids.has(assetUid);
    });
  });

  const missionScopedAssignments = computed(() => {
    const missionUid = selectedMissionUid.value;
    if (!missionUid) {
      return [] as AssignmentRaw[];
    }
    return assignments.value.filter((entry) => String(entry.mission_uid ?? "").trim() === missionUid);
  });

  const missionScopedZones = computed(() => {
    const missionUid = selectedMissionUid.value;
    if (!missionUid) {
      return [] as ZoneRaw[];
    }
    const mission = missions.value.find((entry) => String(entry.uid ?? "").trim() === missionUid);
    const assigned = new Set(
      toArray<string>(mission?.zones)
        .map((item) => String(item ?? "").trim())
        .filter((item) => item.length > 0)
    );
    return zones.value.filter((entry) => assigned.has(String(entry.zone_id ?? "").trim()));
  });

  const setSelectedMissionUid = (value: string) => {
    selectedMissionUid.value = value.trim();
    saveJson(MISSION_SELECTION_STORAGE_KEY, selectedMissionUid.value);
  };

  const restorePersistedSelection = () => {
    if (selectedMissionUid.value) {
      return;
    }
    const persisted = loadJson<string>(MISSION_SELECTION_STORAGE_KEY, "");
    const next = typeof persisted === "string" ? persisted.trim() : "";
    if (next) {
      selectedMissionUid.value = next;
    }
  };

  const ensureSelectedMissionExists = () => {
    if (!missions.value.length) {
      selectedMissionUid.value = "";
      return;
    }
    const selected = selectedMissionUid.value.trim();
    if (!selected) {
      const first = String(missions.value[0]?.uid ?? "").trim();
      setSelectedMissionUid(first);
      return;
    }
    const hasSelected = missions.value.some((entry) => String(entry.uid ?? "").trim() === selected);
    if (!hasSelected) {
      const first = String(missions.value[0]?.uid ?? "").trim();
      setSelectedMissionUid(first);
    }
  };

  const syncRouteQuery = (route: RouteLocationNormalizedLoaded, router: Router) => {
    const selected = selectedMissionUid.value.trim();
    const current = toText(route.query.mission_uid);
    if (current === selected) {
      return;
    }
    const nextQuery = { ...route.query };
    if (selected) {
      nextQuery.mission_uid = selected;
    } else {
      delete nextQuery.mission_uid;
    }
    router.replace({ path: route.path, query: nextQuery }).catch(() => undefined);
  };

  const upsertChecklist = (checklist: ChecklistRaw) => {
    const checklistUid = String(checklist.uid ?? "").trim();
    if (!checklistUid) {
      return;
    }
    const next = [...checklists.value];
    const index = next.findIndex((entry) => String(entry.uid ?? "").trim() === checklistUid);
    if (index >= 0) {
      next[index] = checklist;
    } else {
      next.push(checklist);
    }
    checklists.value = next;
  };

  const hydrateChecklist = async (checklistUid: string): Promise<ChecklistRaw | null> => {
    const uid = checklistUid.trim();
    if (!uid) {
      return null;
    }
    const detail = await get<ChecklistRaw>(`${endpoints.checklists}/${encodeURIComponent(uid)}`);
    upsertChecklist(detail);
    return detail;
  };

  const loadWorkspace = async () => {
    loading.value = true;
    error.value = "";
    try {
      const [
        missionData,
        topicData,
        checklistPayload,
        templatePayload,
        teamData,
        memberData,
        assetData,
        assignmentData,
        eventData,
        missionChangeData,
        logEntryData,
        zoneData,
        skillData,
        teamMemberSkillData,
        taskSkillRequirementData
      ] = await Promise.all([
        get<MissionRaw[]>(endpoints.r3aktMissions),
        get<TopicRaw[]>(endpoints.topics),
        get<{ checklists?: ChecklistRaw[] }>(endpoints.checklists),
        get<{ templates?: TemplateRaw[] }>(endpoints.checklistTemplates),
        get<TeamRaw[]>(endpoints.r3aktTeams),
        get<TeamMemberRaw[]>(endpoints.r3aktTeamMembers),
        get<AssetRaw[]>(endpoints.r3aktAssets),
        get<AssignmentRaw[]>(endpoints.r3aktAssignments),
        get<DomainEventRaw[]>(endpoints.r3aktEvents),
        get<MissionChangeRaw[]>(endpoints.r3aktMissionChanges),
        get<LogEntryRaw[]>(endpoints.r3aktLogEntries),
        get<ZoneRaw[]>(endpoints.zones),
        get<SkillRaw[]>(endpoints.r3aktSkills),
        get<TeamMemberSkillRaw[]>(endpoints.r3aktTeamMemberSkills),
        get<TaskSkillRequirementRaw[]>(endpoints.r3aktTaskSkillRequirements)
      ]);

      missions.value = toArray<MissionRaw>(missionData);
      topics.value = toArray<TopicRaw>(topicData);
      checklists.value = toArray<ChecklistRaw>(checklistPayload.checklists);
      templates.value = toArray<TemplateRaw>(templatePayload.templates);
      teams.value = toArray<TeamRaw>(teamData);
      members.value = toArray<TeamMemberRaw>(memberData);
      assets.value = toArray<AssetRaw>(assetData);
      assignments.value = toArray<AssignmentRaw>(assignmentData);
      events.value = toArray<DomainEventRaw>(eventData);
      missionChanges.value = toArray<MissionChangeRaw>(missionChangeData);
      logEntries.value = toArray<LogEntryRaw>(logEntryData);
      zones.value = toArray<ZoneRaw>(zoneData);
      skills.value = toArray<SkillRaw>(skillData);
      teamMemberSkills.value = toArray<TeamMemberSkillRaw>(teamMemberSkillData);
      taskSkillRequirements.value = toArray<TaskSkillRequirementRaw>(taskSkillRequirementData);
      lastLoadedAt.value = new Date().toISOString();
      restorePersistedSelection();
      ensureSelectedMissionExists();
    } catch (nextError) {
      error.value = nextError instanceof Error ? nextError.message : "Unable to load mission workspace";
      throw nextError;
    } finally {
      loading.value = false;
    }
  };

  return {
    missions,
    topics,
    checklists,
    templates,
    teams,
    members,
    assets,
    assignments,
    events,
    missionChanges,
    logEntries,
    zones,
    skills,
    teamMemberSkills,
    taskSkillRequirements,
    loading,
    error,
    selectedMissionUid,
    lastLoadedAt,
    selectedMission,
    missionSelectOptions,
    missionScopedChecklists,
    missionScopedTeamUids,
    missionScopedMembers,
    missionScopedAssets,
    missionScopedAssignments,
    missionScopedZones,
    setSelectedMissionUid,
    restorePersistedSelection,
    ensureSelectedMissionExists,
    syncRouteQuery,
    hydrateChecklist,
    loadWorkspace
  };
});
