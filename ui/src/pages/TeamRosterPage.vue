<template>
  <div class="team-roster-workspace">
    <div class="registry-shell">
      <header class="registry-top">
        <div class="registry-title">Team Member Assignment</div>
        <div class="registry-status">
          <OnlineHelpLauncher />
          <span class="cui-status-pill" :class="connectionClass">{{ connectionLabel }}</span>
          <span class="cui-status-pill" :class="wsClass">{{ wsLabel }}</span>
          <span class="status-url">{{ baseUrl }}</span>
        </div>
      </header>

      <section class="panel control-strip">
        <div class="control-row">
          <div class="control-actions">
            <BaseButton variant="ghost" size="sm" icon-left="chevron-left" @click="goBackToUsers">
              Users
            </BaseButton>
          </div>
          <div class="control-filters">
            <BaseSelect v-model="selectedTeamUid" label="Team" :options="teamOptions" />
          </div>
          <div class="control-actions">
            <BaseButton variant="secondary" size="sm" icon-left="refresh" @click="loadWorkspace">Refresh</BaseButton>
          </div>
        </div>
        <div class="control-meta">
          <span>Teams: {{ teams.length }}</span>
          <span>Roster Size: {{ membersForTeam.length }}</span>
          <span>Last Refresh: {{ formatTimestamp(lastRefreshedAt) }}</span>
        </div>
      </section>

      <div class="workspace-grid">
        <aside class="panel team-panel">
          <div class="panel-header">
            <div>
              <div class="panel-title">Team Properties</div>
              <div class="panel-subtitle">{{ selectedTeam?.team_name || "No team selected" }}</div>
            </div>
            <div class="panel-chip">{{ membersForTeam.length }} members</div>
          </div>

          <div v-if="!selectedTeam" class="panel-empty">
            Select a team to inspect its profile and manage member assignments.
          </div>
          <template v-else>
            <ul class="stack-list">
              <li>
                <strong>UID</strong>
                <span class="mono">{{ selectedTeam.uid }}</span>
              </li>
              <li>
                <strong>Name</strong>
                <span>{{ selectedTeam.team_name || "-" }}</span>
              </li>
              <li>
                <strong>Color</strong>
                <span>{{ selectedTeam.color || "UNSPECIFIED" }}</span>
              </li>
              <li>
                <strong>Description</strong>
                <span>{{ selectedTeam.team_description || "-" }}</span>
              </li>
              <li>
                <strong>Missions</strong>
                <span>{{ selectedTeamMissionLabels.join(", ") || "-" }}</span>
              </li>
              <li>
                <strong>Updated</strong>
                <span>{{ formatTimestamp(selectedTeam.updated_at || selectedTeam.created_at) }}</span>
              </li>
            </ul>
          </template>
        </aside>

        <section class="panel member-panel">
          <div class="panel-header">
            <div>
              <div class="panel-title">Members</div>
              <div class="panel-subtitle">Assign existing team members or remove them from this team</div>
            </div>
          </div>

          <form class="add-form" @submit.prevent="addMember">
            <BaseSelect v-model="addForm.member_uid" label="Member" :options="availableMemberOptions" />
            <div class="add-actions">
              <BaseButton type="submit" size="sm" icon-left="plus" :disabled="adding || !selectedTeamUid || !addForm.member_uid">
                Add To Team
              </BaseButton>
            </div>
          </form>

          <div v-if="loading" class="panel-empty">Loading team roster...</div>
          <div v-else-if="!selectedTeamUid" class="panel-empty">No team selected.</div>
          <div v-else-if="!membersForTeam.length" class="panel-empty">This team has no assigned members.</div>
          <div v-else class="table-wrap cui-scrollbar">
            <table class="mini-table">
              <thead>
                <tr>
                  <th>Display Name</th>
                  <th>RNS Identity</th>
                  <th>Role</th>
                  <th>Callsign</th>
                  <th>Availability</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="member in membersForTeam" :key="member.uid">
                  <td>{{ member.display_name || "-" }}</td>
                  <td class="mono">{{ member.rns_identity || "-" }}</td>
                  <td>{{ member.role || "TEAM_MEMBER" }}</td>
                  <td>{{ member.callsign || "-" }}</td>
                  <td>{{ member.availability || "-" }}</td>
                  <td>
                    <BaseButton
                      size="sm"
                      variant="danger"
                      icon-left="trash"
                      :disabled="removingUid === member.uid"
                      @click="removeMemberFromTeam(member)"
                    >
                      Remove
                    </BaseButton>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import type { ApiError } from "../api/client";
import { get, post } from "../api/client";
import { endpoints } from "../api/endpoints";
import BaseButton from "../components/BaseButton.vue";
import BaseSelect from "../components/BaseSelect.vue";
import OnlineHelpLauncher from "../components/OnlineHelpLauncher.vue";
import { useConnectionStore } from "../stores/connection";
import { useToastStore } from "../stores/toasts";
import { formatTimestamp } from "../utils/format";

interface MissionRecord {
  uid?: string;
  mission_name?: string | null;
}

interface TeamRecord {
  uid?: string;
  mission_uid?: string | null;
  mission_uids?: string[];
  color?: string | null;
  team_name?: string | null;
  team_description?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

interface TeamMemberRecord {
  uid?: string;
  team_uid?: string | null;
  rns_identity?: string | null;
  display_name?: string | null;
  icon?: string | null;
  role?: string | null;
  callsign?: string | null;
  freq?: number | null;
  email?: string | null;
  phone?: string | null;
  modulation?: string | null;
  availability?: string | null;
  certifications?: string[];
  client_identities?: string[];
}

const toArray = <T>(value: unknown): T[] => (Array.isArray(value) ? (value as T[]) : []);
const toStringList = (value: unknown): string[] =>
  Array.isArray(value)
    ? value.map((item) => String(item ?? "").trim()).filter((item) => item.length > 0)
    : [];
const queryText = (value: unknown): string =>
  Array.isArray(value) ? String(value[0] ?? "").trim() : String(value ?? "").trim();

const route = useRoute();
const router = useRouter();
const connectionStore = useConnectionStore();
const toastStore = useToastStore();

const loading = ref(false);
const adding = ref(false);
const removingUid = ref("");
const lastRefreshedAt = ref("");
const selectedTeamUid = ref("");

const missions = ref<MissionRecord[]>([]);
const teams = ref<TeamRecord[]>([]);
const teamMembers = ref<TeamMemberRecord[]>([]);

const addForm = ref({
  member_uid: ""
});

const baseUrl = computed(() => connectionStore.baseUrlDisplay);
const connectionLabel = computed(() => connectionStore.statusLabel);
const wsLabel = computed(() => connectionStore.wsLabel);

const connectionClass = computed(() => {
  if (connectionStore.status === "online") {
    return "cui-status-success";
  }
  if (connectionStore.status === "offline") {
    return "cui-status-danger";
  }
  return "cui-status-accent";
});

const wsClass = computed(() => {
  if (connectionStore.wsLabel.toLowerCase() === "live") {
    return "cui-status-success";
  }
  return "cui-status-accent";
});

const missionNameByUid = computed(() => {
  const map = new Map<string, string>();
  missions.value.forEach((mission) => {
    const uid = String(mission.uid ?? "").trim();
    if (uid) {
      map.set(uid, String(mission.mission_name ?? uid));
    }
  });
  return map;
});

const teamNameByUid = computed(() => {
  const map = new Map<string, string>();
  teams.value.forEach((team) => {
    const uid = String(team.uid ?? "").trim();
    if (uid) {
      map.set(uid, String(team.team_name ?? uid));
    }
  });
  return map;
});

const teamOptions = computed(() => [
  { label: "Select team", value: "" },
  ...[...teams.value]
    .sort((a, b) => String(a.team_name ?? a.uid ?? "").localeCompare(String(b.team_name ?? b.uid ?? "")))
    .map((team) => ({
      label: String(team.team_name ?? team.uid ?? "Team"),
      value: String(team.uid ?? "")
    }))
]);

const selectedTeam = computed(() => teams.value.find((team) => String(team.uid ?? "") === selectedTeamUid.value));

const selectedTeamMissionLabels = computed(() => {
  if (!selectedTeam.value) {
    return [];
  }
  const missionUids = toStringList(selectedTeam.value.mission_uids);
  const primaryMissionUid = String(selectedTeam.value.mission_uid ?? "").trim();
  if (!missionUids.length && primaryMissionUid) {
    missionUids.push(primaryMissionUid);
  }
  return missionUids.map((uid) => missionNameByUid.value.get(uid) ?? uid);
});

const membersForTeam = computed(() =>
  teamMembers.value
    .filter((member) => String(member.team_uid ?? "").trim() === selectedTeamUid.value)
    .sort((a, b) =>
      String(a.display_name ?? a.rns_identity ?? "").localeCompare(String(b.display_name ?? b.rns_identity ?? ""))
    )
);

const resolveMemberIdentity = (member: TeamMemberRecord): string => {
  const identity = String(member.rns_identity ?? "").trim();
  if (identity) {
    return identity;
  }
  return toStringList(member.client_identities)[0] ?? "";
};

const availableMemberOptions = computed(() => {
  if (!selectedTeamUid.value) {
    return [{ label: "Select team first", value: "" }];
  }
  const selectedMemberUid = addForm.value.member_uid.trim();
  const options = teamMembers.value
    .filter((member) => {
      const memberUid = String(member.uid ?? "").trim();
      if (!memberUid) {
        return false;
      }
      if (memberUid === selectedMemberUid) {
        return true;
      }
      return String(member.team_uid ?? "").trim() !== selectedTeamUid.value;
    })
    .sort((a, b) =>
      String(a.display_name ?? a.rns_identity ?? a.uid ?? "").localeCompare(
        String(b.display_name ?? b.rns_identity ?? b.uid ?? "")
      )
    )
    .map((member) => {
      const uid = String(member.uid ?? "").trim();
      const identity = resolveMemberIdentity(member);
      const displayName = String(member.display_name ?? identity ?? uid).trim() || uid;
      const identitySuffix = identity ? ` (${identity})` : "";
      const assignedTeamUid = String(member.team_uid ?? "").trim();
      let assignmentSuffix = "";
      if (assignedTeamUid && assignedTeamUid !== selectedTeamUid.value) {
        assignmentSuffix = ` - currently in ${teamNameByUid.value.get(assignedTeamUid) ?? assignedTeamUid}`;
      }
      return {
        label: `${displayName}${identitySuffix}${assignmentSuffix}`,
        value: uid
      };
    });

  return [{ label: "Select member", value: "" }, ...options];
});

const selectedMemberToAssign = computed(() => {
  const uid = addForm.value.member_uid.trim();
  if (!uid) {
    return undefined;
  }
  return teamMembers.value.find((member) => String(member.uid ?? "").trim() === uid);
});

const handleApiError = (error: unknown, fallback: string) => {
  const apiError = error as ApiError;
  if (apiError?.status === 401) {
    toastStore.push("Authentication required. Check your credentials.", "warning");
    return;
  }
  if (apiError?.status === 403) {
    toastStore.push("Forbidden. Your account lacks permission for this action.", "warning");
    return;
  }
  toastStore.push(fallback, "danger");
};

const syncRouteWithTeam = (teamUid: string) => {
  const current = queryText(route.query.team_uid);
  if (current === teamUid) {
    return;
  }
  const nextQuery = { ...route.query } as Record<string, string>;
  if (teamUid) {
    nextQuery.team_uid = teamUid;
  } else {
    delete nextQuery.team_uid;
  }
  void router.replace({ query: nextQuery });
};

const chooseInitialTeam = () => {
  if (!teams.value.length) {
    selectedTeamUid.value = "";
    return;
  }
  const queryTeamUid = queryText(route.query.team_uid);
  if (queryTeamUid && teams.value.some((team) => String(team.uid ?? "") === queryTeamUid)) {
    selectedTeamUid.value = queryTeamUid;
    return;
  }
  if (selectedTeamUid.value && teams.value.some((team) => String(team.uid ?? "") === selectedTeamUid.value)) {
    return;
  }
  selectedTeamUid.value = String(teams.value[0]?.uid ?? "");
};

const loadWorkspace = async () => {
  loading.value = true;
  try {
    const [missionData, teamData, teamMemberData] = await Promise.all([
      get<MissionRecord[]>(endpoints.r3aktMissions),
      get<TeamRecord[]>(endpoints.r3aktTeams),
      get<TeamMemberRecord[]>(endpoints.r3aktTeamMembers)
    ]);
    missions.value = toArray<MissionRecord>(missionData);
    teams.value = toArray<TeamRecord>(teamData);
    teamMembers.value = toArray<TeamMemberRecord>(teamMemberData);
    chooseInitialTeam();
    lastRefreshedAt.value = new Date().toISOString();
  } catch (error) {
    handleApiError(error, "Unable to load team roster workspace");
  } finally {
    loading.value = false;
  }
};

const goBackToUsers = () => {
  void router.push("/users");
};

const addMember = async () => {
  const teamUid = selectedTeamUid.value.trim();
  const memberUid = addForm.value.member_uid.trim();
  if (!teamUid) {
    toastStore.push("Select a team first", "warning");
    return;
  }
  if (!memberUid) {
    toastStore.push("Select a team member to assign", "warning");
    return;
  }
  const member = selectedMemberToAssign.value;
  if (!member) {
    toastStore.push("Selected member could not be resolved", "warning");
    return;
  }
  const currentTeamUid = String(member.team_uid ?? "").trim();
  if (currentTeamUid === teamUid) {
    toastStore.push("Selected member is already assigned to this team", "warning");
    return;
  }
  const identity = resolveMemberIdentity(member);
  if (!identity) {
    toastStore.push("Selected member has no RNS identity", "warning");
    return;
  }
  adding.value = true;
  try {
    const derivedDisplayName = String(member.display_name ?? member.callsign ?? identity).trim() || identity;
    const payload = {
      uid: memberUid,
      team_uid: teamUid,
      rns_identity: identity,
      display_name: derivedDisplayName,
      icon: member.icon ?? null,
      role: member.role || "TEAM_MEMBER",
      callsign: member.callsign ?? null,
      availability: member.availability ?? null,
      modulation: member.modulation ?? null,
      email: member.email ?? null,
      phone: member.phone ?? null,
      freq: member.freq ?? null,
      certifications: toStringList(member.certifications)
    };
    await post<TeamMemberRecord>(endpoints.r3aktTeamMembers, payload);
    await loadWorkspace();
    addForm.value.member_uid = "";
    toastStore.push(currentTeamUid ? "Member reassigned to team" : "Member assigned to team", "success");
  } catch (error) {
    handleApiError(error, "Unable to add member to team");
  } finally {
    adding.value = false;
  }
};

const removeMemberFromTeam = async (member: TeamMemberRecord) => {
  const memberUid = String(member.uid ?? "").trim();
  if (!memberUid) {
    return;
  }
  const identity = resolveMemberIdentity(member);
  if (!identity) {
    toastStore.push("Member has no RNS identity", "warning");
    return;
  }
  removingUid.value = memberUid;
  try {
    await post<TeamMemberRecord>(endpoints.r3aktTeamMembers, {
      uid: memberUid,
      team_uid: null,
      rns_identity: identity,
      display_name: String(member.display_name ?? member.callsign ?? identity).trim(),
      icon: member.icon ?? null,
      role: member.role ?? "TEAM_MEMBER",
      callsign: member.callsign ?? null,
      availability: member.availability ?? null,
      modulation: member.modulation ?? null,
      email: member.email ?? null,
      phone: member.phone ?? null,
      freq: member.freq ?? null,
      certifications: toStringList(member.certifications)
    });
    await loadWorkspace();
    toastStore.push("Member removed from team", "warning");
  } catch (error) {
    handleApiError(error, "Unable to remove member from team");
  } finally {
    removingUid.value = "";
  }
};

watch(
  () => route.query.team_uid,
  () => {
    const teamUid = queryText(route.query.team_uid);
    if (!teamUid) {
      return;
    }
    if (teamUid !== selectedTeamUid.value && teams.value.some((team) => String(team.uid ?? "") === teamUid)) {
      selectedTeamUid.value = teamUid;
    }
  }
);

watch(selectedTeamUid, (teamUid) => {
  syncRouteWithTeam(teamUid);
  const selected = selectedMemberToAssign.value;
  if (selected && String(selected.team_uid ?? "").trim() === teamUid) {
    addForm.value.member_uid = "";
  }
});

onMounted(() => {
  loadWorkspace().catch(() => undefined);
});
</script>

<style scoped>
.team-roster-workspace {
  --neon: #37f2ff;
  --panel-dark: rgba(4, 12, 22, 0.96);
  --panel-light: rgba(10, 30, 45, 0.94);
  --amber: #ffb35c;
  color: #dffcff;
  font-family: "Orbitron", "Rajdhani", "Barlow", sans-serif;
}

.registry-shell {
  position: relative;
  padding: 20px 22px 26px;
  border-radius: 18px;
  border: 1px solid rgba(55, 242, 255, 0.25);
  background: radial-gradient(circle at top, rgba(42, 210, 255, 0.12), transparent 55%),
    linear-gradient(145deg, rgba(5, 16, 28, 0.96), rgba(2, 6, 12, 0.98));
  box-shadow: 0 18px 55px rgba(1, 6, 12, 0.65), inset 0 0 0 1px rgba(55, 242, 255, 0.08);
  overflow: hidden;
}

.registry-shell::before {
  content: "";
  position: absolute;
  inset: 0;
  background: radial-gradient(circle at 1px 1px, rgba(55, 242, 255, 0.08) 1px, transparent 0) 0 0 / 18px 18px;
  opacity: 0.6;
  pointer-events: none;
}

.registry-top {
  position: relative;
  display: grid;
  grid-template-columns: 1fr auto;
  align-items: center;
  gap: 16px;
  z-index: 1;
}

.registry-title {
  text-align: center;
  justify-self: center;
  font-size: 20px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #d4fbff;
  text-shadow: 0 0 12px rgba(55, 242, 255, 0.5);
}

.registry-status {
  display: flex;
  align-items: center;
  gap: 10px;
  justify-self: end;
}

.status-url {
  font-size: 11px;
  letter-spacing: 0.08em;
  color: rgba(215, 243, 255, 0.8);
}

.panel {
  position: relative;
  padding: 16px;
  background: linear-gradient(145deg, var(--panel-light), var(--panel-dark));
  border: 1px solid rgba(55, 242, 255, 0.25);
  box-shadow: inset 0 0 0 1px rgba(55, 242, 255, 0.08), 0 12px 30px rgba(1, 6, 12, 0.6);
  clip-path: polygon(0 0, calc(100% - 24px) 0, 100% 24px, 100% 100%, 24px 100%, 0 calc(100% - 24px));
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 14px;
}

.panel-title {
  font-size: 16px;
  text-transform: uppercase;
  letter-spacing: 0.16em;
  color: #d1fbff;
}

.panel-subtitle {
  font-family: "Rajdhani", "Barlow", sans-serif;
  font-size: 12px;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: rgba(209, 251, 255, 0.65);
  margin-top: 4px;
}

.panel-chip {
  border: 1px solid var(--amber);
  color: var(--amber);
  font-size: 11px;
  padding: 4px 10px;
  border-radius: 999px;
  text-transform: uppercase;
  letter-spacing: 0.18em;
  background: rgba(18, 24, 30, 0.6);
}

.control-strip {
  margin-top: 16px;
  z-index: 1;
}

.control-row {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: end;
  gap: 14px;
}

.control-actions {
  display: flex;
  gap: 10px;
}

.control-filters {
  min-width: 0;
}

.control-meta {
  margin-top: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  font-size: 11px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: rgba(204, 247, 255, 0.72);
}

.workspace-grid {
  margin-top: 14px;
  display: grid;
  grid-template-columns: minmax(260px, 340px) 1fr;
  gap: 18px;
  z-index: 1;
  position: relative;
}

.stack-list {
  display: grid;
  gap: 8px;
}

.stack-list li {
  display: grid;
  gap: 4px;
  border: 1px solid rgba(55, 242, 255, 0.18);
  border-radius: 10px;
  padding: 10px 12px;
  background: rgba(6, 18, 30, 0.62);
}

.stack-list strong {
  font-size: 10px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: rgba(206, 249, 255, 0.64);
}

.stack-list span {
  font-size: 12px;
  letter-spacing: 0.08em;
  color: rgba(222, 253, 255, 0.9);
}

.add-form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 12px;
}

.field-control {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field-control span {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  color: rgba(209, 251, 255, 0.66);
}

.field-control input {
  width: 100%;
  background: rgba(6, 16, 25, 0.9);
  border: 1px solid rgba(55, 242, 255, 0.26);
  color: #d8fbff;
  border-radius: 10px;
  padding: 8px 10px;
  font-size: 12px;
  letter-spacing: 0.08em;
}

.add-actions {
  grid-column: 1 / -1;
  display: flex;
  justify-content: flex-end;
}

.selected-user {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  margin-bottom: 12px;
  font-size: 11px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: rgba(196, 248, 255, 0.78);
}

.panel-empty {
  border: 1px dashed rgba(55, 242, 255, 0.25);
  border-radius: 12px;
  text-align: center;
  padding: 18px;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  font-size: 11px;
  color: rgba(209, 251, 255, 0.62);
}

.table-wrap {
  max-height: min(62vh, 640px);
  overflow: auto;
}

.mini-table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
}

.mini-table th,
.mini-table td {
  border-bottom: 1px solid rgba(55, 242, 255, 0.15);
  padding: 9px 10px;
  text-align: left;
  font-size: 12px;
  letter-spacing: 0.08em;
}

.mini-table th {
  text-transform: uppercase;
  font-size: 10px;
  letter-spacing: 0.16em;
  color: rgba(201, 248, 255, 0.68);
}

.mono {
  font-family: "JetBrains Mono", "Cascadia Mono", monospace;
}

:deep(.team-roster-workspace .cui-btn) {
  background: linear-gradient(135deg, rgba(35, 130, 160, 0.45), rgba(6, 18, 28, 0.92));
  border: 1px solid rgba(55, 242, 255, 0.45);
  color: #e5feff;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  font-size: 10px;
}

:deep(.team-roster-workspace .cui-btn--secondary) {
  background: linear-gradient(135deg, rgba(14, 44, 60, 0.85), rgba(6, 14, 22, 0.92));
}

:deep(.team-roster-workspace .cui-combobox__label) {
  font-size: 11px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: rgba(209, 251, 255, 0.66);
}

@media (max-width: 1180px) {
  .workspace-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 760px) {
  .registry-top {
    grid-template-columns: 1fr;
    text-align: center;
  }

  .registry-status {
    justify-content: center;
  }

  .control-row {
    grid-template-columns: 1fr;
  }

  .add-form {
    grid-template-columns: 1fr;
  }
}
</style>
