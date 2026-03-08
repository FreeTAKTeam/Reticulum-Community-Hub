import { computed } from "vue";
import { onMounted } from "vue";
import { ref } from "vue";
import { watch } from "vue";
import type { ComputedRef } from "vue";
import type { Ref } from "vue";

import type { ApiError } from "../api/client";
import { get } from "../api/client";
import { put } from "../api/client";
import { request } from "../api/client";
import { endpoints } from "../api/endpoints";
import type { MissionAccessAssignmentRecord } from "../api/types";
import type { MissionRecord } from "../api/types";
import type { OperationRightGrantRecord } from "../api/types";
import type { RightsDefinitions } from "../api/types";
import type { RightsSubjectRecord } from "../api/types";
import type { TeamMemberRecord } from "../api/types";
import type { TeamRecord } from "../api/types";
import { useToastStore } from "../stores/toasts";
import { resolveTeamMemberPrimaryLabel } from "../utils/team-members";

const TEAM_MEMBER_SUBJECT = "team_member";

type ScopeMode = "global" | "mission";
type ExplicitState = boolean | null;

export interface TeamRightsMatrixMemberRow {
  subjectId: string;
  teamUid: string;
  primaryLabel: string;
  secondaryLabel: string;
  roleLabel: string;
  availabilityLabel: string;
  linkedIdentities: string[];
  missionUids: string[];
  clientCount: number;
}

interface UseTeamRightsMatrixOptions {
  teams: Ref<TeamRecord[]> | ComputedRef<TeamRecord[]>;
  teamMembers: Ref<TeamMemberRecord[]> | ComputedRef<TeamMemberRecord[]>;
  missions: Ref<MissionRecord[]> | ComputedRef<MissionRecord[]>;
}

const normalizeText = (value: unknown): string => String(value ?? "").trim();
const normalizeIdentity = (value: unknown): string => normalizeText(value).toLowerCase();
const uniqueValues = (values: string[]): string[] => [...new Set(values.filter((value) => value.length > 0))];

const operationKey = (subjectId: string, operation: string): string => `${subjectId}::${operation}`;

const extractTeamMissionUids = (team?: TeamRecord | null): string[] => {
  if (!team) {
    return [];
  }
  const missionUids = Array.isArray(team.mission_uids)
    ? team.mission_uids.map((item) => normalizeText(item))
    : [];
  const legacyMissionUid = normalizeText(team.mission_uid);
  if (legacyMissionUid) {
    missionUids.push(legacyMissionUid);
  }
  return uniqueValues(missionUids);
};

const buildErrorMessage = (error: unknown, fallback: string): string => {
  const apiError = error as ApiError;
  if (apiError?.status === 401) {
    return "Authentication required. Check your credentials.";
  }
  if (apiError?.status === 403) {
    return "Access denied. This operator is not authorized for rights management.";
  }
  if (typeof apiError?.body === "object" && apiError.body && "detail" in apiError.body) {
    return String((apiError.body as { detail?: unknown }).detail ?? fallback);
  }
  return apiError?.message || fallback;
};

export const useTeamRightsMatrix = (options: UseTeamRightsMatrixOptions) => {
  const toastStore = useToastStore();

  const loading = ref(false);
  const saving = ref(false);
  const initialized = ref(false);
  const definitions = ref<RightsDefinitions | null>(null);
  const subjects = ref<RightsSubjectRecord[]>([]);
  const selectedTeamUid = ref("");
  const selectedMissionUid = ref("");
  const scopeMode = ref<ScopeMode>("mission");
  const memberFilter = ref("");
  const operationFilter = ref("");
  const baselineRoleBySubject = ref<Record<string, string>>({});
  const baselineExplicitByCell = ref<Record<string, ExplicitState>>({});
  const roleDraftBySubject = ref<Record<string, string>>({});
  const operationDraftByCell = ref<Record<string, boolean>>({});

  const operationList = computed(() => definitions.value?.operations ?? []);
  const missionRoleBundles = computed(() => definitions.value?.mission_role_bundles ?? {});
  const subjectById = computed(() => {
    const map = new Map<string, RightsSubjectRecord>();
    subjects.value.forEach((subject) => {
      const subjectId = normalizeText(subject.subject_id);
      if (subjectId) {
        map.set(subjectId, subject);
      }
    });
    return map;
  });

  const sortedTeams = computed(() =>
    [...options.teams.value].sort((left, right) =>
      normalizeText(left.team_name || left.uid).localeCompare(normalizeText(right.team_name || right.uid))
    )
  );

  const selectedTeam = computed(() =>
    sortedTeams.value.find((team) => normalizeText(team.uid) === normalizeText(selectedTeamUid.value)) ?? null
  );

  const linkedMissionSet = computed(() => new Set(extractTeamMissionUids(selectedTeam.value)));
  const associatedTeamUidForSelectedMission = computed(() => {
    const missionUid = normalizeText(selectedMissionUid.value);
    if (!missionUid) {
      return "";
    }
    return (
      normalizeText(
        sortedTeams.value.find((team) => extractTeamMissionUids(team).includes(missionUid))?.uid
      ) || ""
    );
  });

  const missionOptions = computed(() => {
    const linkedUids = linkedMissionSet.value;
    const sortedMissions = [...options.missions.value].sort((left, right) =>
      normalizeText(left.mission_name || left.uid).localeCompare(normalizeText(right.mission_name || right.uid))
    );
    return sortedMissions.map((mission) => {
      const missionUid = normalizeText(mission.uid);
      const missionName = normalizeText(mission.mission_name) || missionUid || "Unnamed mission";
      return {
        label: linkedUids.has(missionUid) ? `${missionName} (linked)` : missionName,
        value: missionUid
      };
    });
  });

  const roleOptions = computed(() => [
    { label: "No bundle", value: "" },
    ...Object.keys(missionRoleBundles.value).map((role) => ({
      label: role.replaceAll("_", " "),
      value: role
    }))
  ]);

  const teamOptions = computed(() => [
    { label: "No team selected", value: "" },
    ...sortedTeams.value.map((team) => ({
      label: normalizeText(team.team_name) || normalizeText(team.uid) || "Unnamed team",
      value: normalizeText(team.uid)
    }))
  ]);

  const getRoleDraft = (subjectId: string): string => {
    if (scopeMode.value !== "mission") {
      return "";
    }
    return roleDraftBySubject.value[subjectId] ?? baselineRoleBySubject.value[subjectId] ?? "";
  };

  const roleProvidesOperation = (role: string, operation: string): boolean =>
    Boolean(missionRoleBundles.value[role]?.includes(operation));

  const getBaselineExplicit = (subjectId: string, operation: string): ExplicitState => {
    const key = operationKey(subjectId, operation);
    return baselineExplicitByCell.value[key] ?? null;
  };

  const computeBaseCellValue = (subjectId: string, operation: string): boolean => {
    const explicitState = getBaselineExplicit(subjectId, operation);
    if (explicitState === true) {
      return true;
    }
    if (explicitState === false) {
      return false;
    }
    return roleProvidesOperation(getRoleDraft(subjectId), operation);
  };

  const cellEnabled = (subjectId: string, operation: string): boolean => {
    const key = operationKey(subjectId, operation);
    return operationDraftByCell.value[key] ?? computeBaseCellValue(subjectId, operation);
  };

  const cellSource = (subjectId: string, operation: string): "draft" | "grant" | "deny" | "role" | "none" => {
    const key = operationKey(subjectId, operation);
    if (key in operationDraftByCell.value) {
      return "draft";
    }
    const explicitState = getBaselineExplicit(subjectId, operation);
    if (explicitState === true) {
      return "grant";
    }
    if (explicitState === false) {
      return "deny";
    }
    return roleProvidesOperation(getRoleDraft(subjectId), operation) ? "role" : "none";
  };

  const teamMembersForSelectedTeam = computed(() => {
    const teamUid = normalizeText(selectedTeamUid.value);
    if (!teamUid) {
      return [] as TeamMemberRecord[];
    }
    return options.teamMembers.value.filter((member) => normalizeText(member.team_uid) === teamUid);
  });

  const filteredMembers = computed<TeamRightsMatrixMemberRow[]>(() => {
    const filter = normalizeIdentity(memberFilter.value);
    return [...teamMembersForSelectedTeam.value]
      .map((member) => {
        const subjectId = normalizeText(member.uid);
        const subject = subjectById.value.get(subjectId);
        const linkedIdentities = uniqueValues([
          ...(Array.isArray(subject?.client_identities) ? subject.client_identities.map((item) => normalizeText(item)) : []),
          ...(Array.isArray(member.client_identities) ? member.client_identities.map((item) => normalizeText(item)) : [])
        ]);
        return {
          subjectId,
          teamUid: normalizeText(member.team_uid),
          primaryLabel: resolveTeamMemberPrimaryLabel(member, {
            identity: subject?.rns_identity ?? member.rns_identity,
            uid: member.uid
          }),
          secondaryLabel: normalizeText(subject?.rns_identity ?? member.rns_identity) || "No linked identity",
          roleLabel: normalizeText(member.role) || "TEAM_MEMBER",
          availabilityLabel: normalizeText(member.availability) || "Unknown",
          linkedIdentities,
          missionUids: subject?.mission_uids ?? [],
          clientCount: linkedIdentities.length
        };
      })
      .filter((member) => {
        if (!member.subjectId) {
          return false;
        }
        if (!filter) {
          return true;
        }
        return [
          member.primaryLabel,
          member.secondaryLabel,
          member.roleLabel,
          member.availabilityLabel,
          ...member.linkedIdentities
        ]
          .join(" ")
          .toLowerCase()
          .includes(filter);
      })
      .sort((left, right) => left.primaryLabel.localeCompare(right.primaryLabel));
  });

  const visibleOperations = computed(() => {
    const filter = normalizeIdentity(operationFilter.value);
    return operationList.value.filter((operation) => {
      if (!filter) {
        return true;
      }
      return operation.toLowerCase().includes(filter) || operation.replaceAll(".", " ").toLowerCase().includes(filter);
    });
  });

  const hasDraftChanges = computed(
    () => Object.keys(roleDraftBySubject.value).length > 0 || Object.keys(operationDraftByCell.value).length > 0
  );

  const resetDraft = () => {
    roleDraftBySubject.value = {};
    operationDraftByCell.value = {};
  };

  const pruneOperationDrafts = (subjectId: string) => {
    Object.keys(operationDraftByCell.value)
      .filter((key) => key.startsWith(`${subjectId}::`))
      .forEach((key) => {
        const operation = key.slice(subjectId.length + 2);
        if (operationDraftByCell.value[key] === computeBaseCellValue(subjectId, operation)) {
          delete operationDraftByCell.value[key];
        }
      });
  };

  const setMissionRole = (subjectId: string, role: string) => {
    if (scopeMode.value !== "mission") {
      return;
    }
    const normalizedSubjectId = normalizeText(subjectId);
    const normalizedRole = normalizeText(role);
    const baselineRole = baselineRoleBySubject.value[normalizedSubjectId] ?? "";
    if (normalizedRole === baselineRole) {
      delete roleDraftBySubject.value[normalizedSubjectId];
    } else {
      roleDraftBySubject.value[normalizedSubjectId] = normalizedRole;
    }
    pruneOperationDrafts(normalizedSubjectId);
  };

  const toggleOperation = (subjectId: string, operation: string) => {
    const normalizedSubjectId = normalizeText(subjectId);
    const normalizedOperation = normalizeText(operation);
    const key = operationKey(normalizedSubjectId, normalizedOperation);
    const baseValue = computeBaseCellValue(normalizedSubjectId, normalizedOperation);
    const currentValue = operationDraftByCell.value[key] ?? baseValue;
    const nextValue = !currentValue;
    if (nextValue === baseValue) {
      delete operationDraftByCell.value[key];
      return;
    }
    operationDraftByCell.value[key] = nextValue;
  };

  const revokeVisible = () => {
    filteredMembers.value.forEach((member) => {
      if (scopeMode.value === "mission") {
        setMissionRole(member.subjectId, "");
      }
      visibleOperations.value.forEach((operation) => {
        const key = operationKey(member.subjectId, operation);
        const baseValue = computeBaseCellValue(member.subjectId, operation);
        if (baseValue === false) {
          delete operationDraftByCell.value[key];
        } else {
          operationDraftByCell.value[key] = false;
        }
      });
    });
  };

  const loadDefinitionsAndSubjects = async () => {
    const [definitionsResponse, subjectsResponse] = await Promise.all([
      get<RightsDefinitions>(endpoints.r3aktRightsDefinitions),
      get<RightsSubjectRecord[]>(endpoints.r3aktRightsSubjects)
    ]);
    definitions.value = definitionsResponse;
    subjects.value = subjectsResponse.filter((subject) => normalizeText(subject.subject_type) === TEAM_MEMBER_SUBJECT);
  };

  const loadScopeData = async () => {
    const scope = scopeMode.value;
    const missionUid = normalizeText(selectedMissionUid.value);
    if (scope === "mission" && !missionUid) {
      baselineRoleBySubject.value = {};
      baselineExplicitByCell.value = {};
      resetDraft();
      return;
    }

    loading.value = true;
    try {
      const grantsUrl = new URLSearchParams({
        subject_type: TEAM_MEMBER_SUBJECT,
        scope_type: scope
      });
      if (scope === "mission") {
        grantsUrl.set("scope_id", missionUid);
      }

      const requests: [Promise<OperationRightGrantRecord[]>, Promise<MissionAccessAssignmentRecord[]>] = [
        get<OperationRightGrantRecord[]>(`${endpoints.r3aktRightsGrants}?${grantsUrl.toString()}`),
        scope === "mission"
          ? get<MissionAccessAssignmentRecord[]>(
              `${endpoints.r3aktMissionAccess}?${new URLSearchParams({ mission_uid: missionUid }).toString()}`
            )
          : Promise.resolve([])
      ];

      const [grantRecords, accessRecords] = await Promise.all(requests);
      const nextExplicit: Record<string, ExplicitState> = {};
      grantRecords
        .filter((record) => normalizeText(record.subject_type) === TEAM_MEMBER_SUBJECT)
        .forEach((record) => {
          nextExplicit[operationKey(normalizeText(record.subject_id), normalizeText(record.operation))] = Boolean(record.granted);
        });

      const nextRoles: Record<string, string> = {};
      accessRecords
        .filter((record) => normalizeText(record.subject_type) === TEAM_MEMBER_SUBJECT)
        .forEach((record) => {
          nextRoles[normalizeText(record.subject_id)] = normalizeText(record.role);
        });

      baselineExplicitByCell.value = nextExplicit;
      baselineRoleBySubject.value = nextRoles;
      resetDraft();
    } catch (error) {
      toastStore.push(buildErrorMessage(error, "Unable to load rights assignments."), "danger");
    } finally {
      loading.value = false;
    }
  };

  const refresh = async () => {
    loading.value = true;
    try {
      await loadDefinitionsAndSubjects();
      await loadScopeData();
      initialized.value = true;
    } catch (error) {
      toastStore.push(buildErrorMessage(error, "Unable to load rights matrix."), "danger");
    } finally {
      loading.value = false;
    }
  };

  const applyChanges = async () => {
    const subjectIds = teamMembersForSelectedTeam.value
      .map((member) => normalizeText(member.uid))
      .filter((value) => value.length > 0);
    if (!subjectIds.length || !definitions.value) {
      return;
    }

    saving.value = true;
    try {
      const missionUid = normalizeText(selectedMissionUid.value);
      if (scopeMode.value === "mission" && missionUid) {
        for (const subjectId of subjectIds) {
          const baselineRole = baselineRoleBySubject.value[subjectId] ?? "";
          const nextRole = getRoleDraft(subjectId);
          if (baselineRole === nextRole) {
            continue;
          }
          if (nextRole) {
            await put<MissionAccessAssignmentRecord>(endpoints.r3aktMissionAccess, {
              mission_uid: missionUid,
              subject_type: TEAM_MEMBER_SUBJECT,
              subject_id: subjectId,
              role: nextRole,
              assigned_by: "ui"
            });
            continue;
          }
          await request<void>(endpoints.r3aktMissionAccess, {
            method: "DELETE",
            body: {
              mission_uid: missionUid,
              subject_type: TEAM_MEMBER_SUBJECT,
              subject_id: subjectId
            }
          });
        }
      }

      for (const subjectId of subjectIds) {
        const nextRole = getRoleDraft(subjectId);
        for (const operation of operationList.value) {
          const draftEffective = cellEnabled(subjectId, operation);
          const baselineExplicit = getBaselineExplicit(subjectId, operation);
          const nextRoleProvides = scopeMode.value === "mission" && roleProvidesOperation(nextRole, operation);

          let desiredExplicit: ExplicitState = null;
          if (!draftEffective) {
            if (nextRoleProvides || baselineExplicit === true || baselineExplicit === false) {
              desiredExplicit = false;
            }
          } else if (nextRoleProvides) {
            if (baselineExplicit === false || baselineExplicit === true) {
              desiredExplicit = true;
            }
          } else {
            desiredExplicit = true;
          }

          if (desiredExplicit === baselineExplicit || desiredExplicit === null) {
            continue;
          }

          const payload = {
            subject_type: TEAM_MEMBER_SUBJECT,
            subject_id: subjectId,
            operation,
            scope_type: scopeMode.value,
            scope_id: scopeMode.value === "mission" ? missionUid : null,
            granted_by: "ui"
          };
          if (desiredExplicit) {
            await put<OperationRightGrantRecord>(endpoints.r3aktRightsGrants, payload);
            continue;
          }
          await request<void>(endpoints.r3aktRightsGrants, {
            method: "DELETE",
            body: payload
          });
        }
      }

      await loadScopeData();
      toastStore.push("Rights assignments updated.", "success");
    } catch (error) {
      toastStore.push(buildErrorMessage(error, "Unable to apply rights changes."), "danger");
    } finally {
      saving.value = false;
    }
  };

  watch(
    () => sortedTeams.value.map((team) => normalizeText(team.uid)),
    (teamUids) => {
      if (teamUids.length === 0) {
        selectedTeamUid.value = "";
        return;
      }
      const currentTeamUid = normalizeText(selectedTeamUid.value);
      if (!currentTeamUid) {
        if (scopeMode.value === "mission" && normalizeText(selectedMissionUid.value)) {
          return;
        }
        selectedTeamUid.value = teamUids[0];
        return;
      }
      if (!teamUids.includes(currentTeamUid)) {
        selectedTeamUid.value = associatedTeamUidForSelectedMission.value || teamUids[0];
      }
    },
    { immediate: true }
  );

  watch(
    () => missionOptions.value.map((mission) => mission.value),
    (missionUids) => {
      if (scopeMode.value !== "mission") {
        return;
      }
      if (missionUids.length === 0) {
        selectedMissionUid.value = "";
        return;
      }
      const linkedMissionUid = missionOptions.value.find((mission) => linkedMissionSet.value.has(mission.value))?.value;
      if (!missionUids.includes(normalizeText(selectedMissionUid.value))) {
        selectedMissionUid.value = linkedMissionUid ?? missionUids[0];
      }
    },
    { immediate: true }
  );

  watch(scopeMode, (mode) => {
    if (mode === "global") {
      resetDraft();
      return;
    }
    if (!selectedMissionUid.value && missionOptions.value.length > 0) {
      selectedMissionUid.value = missionOptions.value[0].value;
    }
  });

  watch(
    () => [scopeMode.value, selectedMissionUid.value, associatedTeamUidForSelectedMission.value],
    ([mode, missionUid, associatedTeamUid]) => {
      if (mode !== "mission") {
        return;
      }
      if (!normalizeText(missionUid)) {
        return;
      }
      selectedTeamUid.value = normalizeText(associatedTeamUid);
    }
  );

  watch(
    () => [scopeMode.value, selectedMissionUid.value],
    () => {
      if (!initialized.value) {
        return;
      }
      void loadScopeData();
    }
  );

  onMounted(() => {
    void refresh();
  });

  return {
    loading,
    saving,
    definitions,
    selectedTeamUid,
    selectedMissionUid,
    scopeMode,
    memberFilter,
    operationFilter,
    filteredMembers,
    hasDraftChanges,
    missionOptions,
    roleOptions,
    teamOptions,
    visibleOperations,
    cellEnabled,
    cellSource,
    getRoleDraft,
    refresh,
    applyChanges,
    resetDraft,
    revokeVisible,
    setMissionRole,
    toggleOperation
  };
};
