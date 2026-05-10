<template>
  <CosmicPanel class="rights-panel">
    <CosmicPanelHeader title="Team Rights Matrix" subtitle="Mission bundles and explicit operation rights for team members">
      <div class="rights-summary">
        <CosmicBadge tone="info">{{ filteredMembers.length }} members</CosmicBadge>
        <CosmicBadge tone="warning">{{ visibleOperations.length }} rights</CosmicBadge>
        <CosmicBadge v-if="scopeMode === 'mission' && selectedMissionUid" tone="success">
          {{ selectedMissionLabel }}
        </CosmicBadge>
        <CosmicBadge v-if="hasDraftChanges" tone="primary">Draft pending</CosmicBadge>
      </div>
    </CosmicPanelHeader>

    <div class="rights-toolbar">
      <BaseSelect v-model="selectedTeamUid" label="Team" :options="teamOptions" />
      <BaseSelect v-model="scopeMode" label="Scope" :options="scopeOptions" />
      <BaseSelect
        v-if="scopeMode === 'mission'"
        v-model="selectedMissionUid"
        label="Mission"
        :options="missionOptions"
        :disabled="missionOptions.length === 0"
      />
      <label class="rights-filter">
        <span>Member Filter</span>
        <input v-model="memberFilter" type="text" placeholder="Callsign, role, identity" />
      </label>
      <label class="rights-filter">
        <span>Rights Filter</span>
        <input v-model="operationFilter" type="text" placeholder="Search operations" />
      </label>
    </div>

    <div class="rights-bundles" v-if="scopeMode === 'mission'">
      <div v-for="bundle in bundleSummaries" :key="bundle.role" class="rights-bundle-card">
        <CosmicBadge tone="info">{{ bundle.roleLabel }}</CosmicBadge>
        <span>{{ bundle.operationCount }} mapped operations</span>
      </div>
    </div>

    <div class="rights-actions">
      <div class="rights-advisory">
        <CosmicBadge tone="warning">Sticky Overrides</CosmicBadge>
        <span>Explicit allow/deny changes persist after role updates until the backend adds clear-to-inherit support.</span>
      </div>
      <div class="rights-action-buttons">
        <BaseButton variant="secondary" icon-left="refresh" :disabled="saving" @click="refresh">Refresh</BaseButton>
        <BaseButton variant="ghost" icon-left="undo" :disabled="saving || !hasDraftChanges" @click="resetDraft">
          Reset Draft
        </BaseButton>
        <BaseButton variant="secondary" icon-left="ban" :disabled="saving || !filteredMembers.length" @click="revokeVisible">
          Revoke Visible
        </BaseButton>
        <BaseButton icon-left="save" :loading="saving" :disabled="loading || !hasDraftChanges" @click="applyChanges">
          Apply Changes
        </BaseButton>
      </div>
    </div>

    <div v-if="!props.teams.length" class="rights-empty">Create a team before assigning team member rights.</div>
    <div v-else-if="scopeMode === 'mission' && !selectedMissionUid" class="rights-empty">
      Select a mission to manage mission access bundles and scoped rights.
    </div>
    <div v-else-if="loading" class="rights-empty">Loading rights matrix...</div>
    <div v-else-if="!visibleOperations.length" class="rights-empty">No rights match the current operation filter.</div>
    <div v-else-if="!filteredMembers.length" class="rights-empty">No team members match the current selection.</div>
    <div v-else class="rights-matrix-shell">
      <div ref="matrixViewportRef" class="rights-matrix-wrap" @scroll="onMatrixScroll">
        <table ref="matrixTableRef" class="rights-matrix">
        <thead>
          <tr>
            <th class="rights-col-member">Identity / Member</th>
            <th v-if="scopeMode === 'mission'" class="rights-col-role">Mission Access</th>
            <th v-for="operation in visibleOperations" :key="operation" class="rights-col-operation" :title="operation">
              <div class="rights-op-label">{{ formatOperationLabel(operation) }}</div>
              <div class="rights-op-code mono">{{ operation }}</div>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="member in filteredMembers" :key="member.subjectId">
            <td class="rights-member-cell">
              <div class="rights-member-avatar">{{ memberInitials(member.primaryLabel) }}</div>
              <div class="rights-member-copy">
                <div class="rights-member-name">{{ member.primaryLabel }}</div>
                <div class="rights-member-secondary mono">{{ member.secondaryLabel }}</div>
                <div class="rights-member-meta">
                  <CosmicBadge tone="neutral">{{ member.roleLabel }}</CosmicBadge>
                  <CosmicBadge tone="info">{{ member.clientCount }} linked</CosmicBadge>
                  <CosmicBadge v-if="member.availabilityLabel !== 'Unknown'" tone="warning">
                    {{ member.availabilityLabel }}
                  </CosmicBadge>
                </div>
              </div>
            </td>
            <td v-if="scopeMode === 'mission'" class="rights-role-cell">
              <select
                class="rights-role-select"
                :value="getRoleDraft(member.subjectId)"
                @change="onRoleChange(member.subjectId, $event)"
              >
                <option v-for="option in roleOptions" :key="option.value || 'none'" :value="option.value">
                  {{ option.label }}
                </option>
              </select>
            </td>
            <td v-for="operation in visibleOperations" :key="`${member.subjectId}-${operation}`" class="rights-cell-shell">
              <button
                class="rights-cell"
                :class="cellClass(member.subjectId, operation)"
                type="button"
                :aria-pressed="cellEnabled(member.subjectId, operation)"
                :title="cellTitle(member.subjectId, operation)"
                @click="toggleOperation(member.subjectId, operation)"
              >
                <span class="rights-cell-indicator" aria-hidden="true">
                  {{ cellEnabled(member.subjectId, operation) ? "✓" : "" }}
                </span>
              </button>
            </td>
          </tr>
        </tbody>
        </table>
      </div>
      <div v-if="showHorizontalScrollbar" ref="scrollbarRef" class="rights-scrollbar" @scroll="onScrollbarScroll">
        <div class="rights-scrollbar-track" :style="{ width: `${scrollbarContentWidth}px` }"></div>
      </div>
    </div>
  </CosmicPanel>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { nextTick } from "vue";
import { onBeforeUnmount } from "vue";
import { onMounted } from "vue";
import { ref } from "vue";
import { toRef } from "vue";
import { watch } from "vue";

import type { MissionRecord } from "../../api/types";
import type { TeamMemberRecord } from "../../api/types";
import type { TeamRecord } from "../../api/types";
import BaseButton from "../BaseButton.vue";
import BaseSelect from "../BaseSelect.vue";
import CosmicBadge from "../cosmic/CosmicBadge.vue";
import CosmicPanel from "../cosmic/CosmicPanel.vue";
import CosmicPanelHeader from "../cosmic/CosmicPanelHeader.vue";
import { useTeamRightsMatrix } from "../../composables/useTeamRightsMatrix";

const props = defineProps<{
  teams: TeamRecord[];
  teamMembers: TeamMemberRecord[];
  missions: MissionRecord[];
}>();

const matrixViewportRef = ref<HTMLDivElement | null>(null);
const matrixTableRef = ref<HTMLTableElement | null>(null);
const scrollbarRef = ref<HTMLDivElement | null>(null);
const scrollbarContentWidth = ref(0);
const showHorizontalScrollbar = ref(false);
let resizeObserver: ResizeObserver | null = null;
let syncingFromMatrix = false;
let syncingFromScrollbar = false;

const {
  definitions,
  loading,
  saving,
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
} = useTeamRightsMatrix({
  teams: toRef(props, "teams"),
  teamMembers: toRef(props, "teamMembers"),
  missions: toRef(props, "missions")
});

const scopeOptions = [
  { label: "Mission", value: "mission" },
  { label: "Global", value: "global" }
];

const missionNameByUid = computed(() => {
  const map = new Map<string, string>();
  props.missions.forEach((mission) => {
    const missionUid = String(mission.uid ?? "").trim();
    if (!missionUid) {
      return;
    }
    map.set(missionUid, String(mission.mission_name ?? missionUid).trim() || missionUid);
  });
  return map;
});

const selectedMissionLabel = computed(() => {
  const missionUid = String(selectedMissionUid.value ?? "").trim();
  if (!missionUid) {
    return "No mission";
  }
  return missionNameByUid.value.get(missionUid) ?? missionUid;
});

const bundleSummaries = computed(() =>
  roleOptions.value
    .filter((option) => option.value.length > 0)
    .map((option) => ({
      role: option.value,
      roleLabel: option.label,
      operationCount: definitions.value?.mission_role_bundles[option.value]?.length ?? 0
    }))
);

const operationSegmentAliases: Record<string, string> = {
  mission: "Mission",
  registry: "Registry",
  assignment: "Assign",
  checklist: "Checklist",
  template: "Template",
  content: "Content",
  message: "Message",
  zone: "Zone",
  audit: "Audit",
  topic: "Topic",
  write: "Write",
  read: "Read",
  delete: "Delete",
  create: "Create",
  send: "Send",
  join: "Join",
  leave: "Leave",
  subscribe: "Subscribe",
  upload: "Upload",
  publish: "Publish",
  asset: "Asset",
  skill: "Skill",
  team: "Team",
  log: "Log",
  r3akt: "R3AKT",
  feed: "Feed"
};

const formatOperationLabel = (operation: string): string =>
  operation
    .split(".")
    .slice(-2)
    .map((segment) => operationSegmentAliases[segment] ?? segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(" ");

const memberInitials = (label: string): string => {
  const parts = label
    .split(/\s+/)
    .map((part) => part.trim())
    .filter((part) => part.length > 0);
  return parts.slice(0, 2).map((part) => part[0]?.toUpperCase() ?? "").join("") || "TM";
};

const onRoleChange = (subjectId: string, event: Event) => {
  const target = event.target as HTMLSelectElement;
  setMissionRole(subjectId, target.value);
};

const cellClass = (subjectId: string, operation: string) => {
  const enabled = cellEnabled(subjectId, operation);
  return {
    "is-enabled": enabled,
    "is-disabled": !enabled,
    "is-draft": cellSource(subjectId, operation) === "draft",
    "is-grant": cellSource(subjectId, operation) === "grant",
    "is-deny": cellSource(subjectId, operation) === "deny",
    "is-role": cellSource(subjectId, operation) === "role"
  };
};

const cellTitle = (subjectId: string, operation: string): string => {
  const source = cellSource(subjectId, operation);
  const enabled = cellEnabled(subjectId, operation);
  const stateLabel = enabled ? "Allowed" : "Denied";
  if (source === "draft") {
    return `${formatOperationLabel(operation)}: ${stateLabel} (draft change)`;
  }
  if (source === "grant") {
    return `${formatOperationLabel(operation)}: ${stateLabel} via explicit grant`;
  }
  if (source === "deny") {
    return `${formatOperationLabel(operation)}: ${stateLabel} via explicit revoke`;
  }
  if (source === "role") {
    return `${formatOperationLabel(operation)}: ${stateLabel} via mission access bundle`;
  }
  return `${formatOperationLabel(operation)}: ${stateLabel}`;
};

const syncScrollbarMetrics = async () => {
  await nextTick();
  const viewport = matrixViewportRef.value;
  const table = matrixTableRef.value;
  const scrollbar = scrollbarRef.value;
  if (!viewport || !table) {
    scrollbarContentWidth.value = 0;
    showHorizontalScrollbar.value = false;
    return;
  }
  const contentWidth = Math.ceil(table.scrollWidth);
  const viewportWidth = Math.ceil(viewport.clientWidth);
  scrollbarContentWidth.value = contentWidth;
  showHorizontalScrollbar.value = contentWidth > viewportWidth;
  if (scrollbar) {
    scrollbar.scrollLeft = viewport.scrollLeft;
  }
};

const onMatrixScroll = () => {
  if (syncingFromScrollbar) {
    return;
  }
  const viewport = matrixViewportRef.value;
  const scrollbar = scrollbarRef.value;
  if (!viewport || !scrollbar) {
    return;
  }
  syncingFromMatrix = true;
  scrollbar.scrollLeft = viewport.scrollLeft;
  syncingFromMatrix = false;
};

const onScrollbarScroll = () => {
  if (syncingFromMatrix) {
    return;
  }
  const viewport = matrixViewportRef.value;
  const scrollbar = scrollbarRef.value;
  if (!viewport || !scrollbar) {
    return;
  }
  syncingFromScrollbar = true;
  viewport.scrollLeft = scrollbar.scrollLeft;
  syncingFromScrollbar = false;
};

onMounted(() => {
  void syncScrollbarMetrics();
  window.addEventListener("resize", syncScrollbarMetrics);
  if (typeof ResizeObserver !== "undefined") {
    resizeObserver = new ResizeObserver(() => {
      void syncScrollbarMetrics();
    });
    if (matrixViewportRef.value) {
      resizeObserver.observe(matrixViewportRef.value);
    }
    if (matrixTableRef.value) {
      resizeObserver.observe(matrixTableRef.value);
    }
  }
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", syncScrollbarMetrics);
  resizeObserver?.disconnect();
  resizeObserver = null;
});

watch(
  () => [visibleOperations.value.length, filteredMembers.value.length, scopeMode.value, selectedMissionUid.value, selectedTeamUid.value],
  () => {
    void syncScrollbarMetrics();
  },
  { flush: "post" }
);
</script>

<style scoped>
.rights-panel {
  position: relative;
  overflow: hidden;
  border: 1px solid rgba(55, 242, 255, 0.24);
  background:
    linear-gradient(180deg, rgba(2, 15, 25, 0.98), rgba(4, 12, 20, 0.92)),
    repeating-linear-gradient(
      180deg,
      rgba(55, 242, 255, 0.03) 0,
      rgba(55, 242, 255, 0.03) 1px,
      transparent 1px,
      transparent 5px
    );
  box-shadow: inset 0 0 0 1px rgba(55, 242, 255, 0.08), 0 18px 48px rgba(0, 0, 0, 0.32);
}

.rights-summary {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}

.rights-toolbar {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
  margin-top: 16px;
}

.rights-filter {
  display: grid;
  gap: 6px;
}

.rights-filter span {
  font-size: 11px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: rgba(209, 251, 255, 0.66);
}

.rights-filter input {
  width: 100%;
  border: 1px solid rgba(55, 242, 255, 0.24);
  border-radius: 10px;
  background: rgba(4, 18, 28, 0.84);
  color: #dffcff;
  padding: 10px 12px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.rights-filter input::placeholder {
  color: rgba(209, 251, 255, 0.4);
}

.rights-bundles {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 16px;
}

.rights-bundle-card {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 12px;
  border: 1px solid rgba(55, 242, 255, 0.18);
  background: rgba(3, 16, 25, 0.74);
  color: rgba(216, 250, 255, 0.84);
  font-size: 12px;
  letter-spacing: 0.08em;
}

.rights-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-top: 18px;
  flex-wrap: wrap;
}

.rights-advisory {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  color: rgba(214, 250, 255, 0.78);
  font-size: 12px;
  letter-spacing: 0.06em;
}

.rights-action-buttons {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.rights-empty {
  margin-top: 18px;
  padding: 24px;
  text-align: center;
  border: 1px dashed rgba(55, 242, 255, 0.24);
  border-radius: 14px;
  color: rgba(210, 251, 255, 0.7);
  text-transform: uppercase;
  letter-spacing: 0.18em;
  font-size: 12px;
}

.rights-matrix-shell {
  margin-top: 18px;
}

.rights-scrollbar {
  position: sticky;
  bottom: 0;
  z-index: 8;
  overflow-x: scroll;
  overflow-y: hidden;
  height: 22px;
  margin-top: 10px;
  border-radius: 999px;
  border: 1px solid rgba(55, 242, 255, 0.18);
  background: rgba(2, 14, 22, 0.88);
  scrollbar-color: rgba(55, 242, 255, 0.72) rgba(4, 17, 26, 0.95);
  scrollbar-width: auto;
}

.rights-scrollbar-track {
  min-width: 100%;
  height: 20px;
}

.rights-scrollbar::-webkit-scrollbar {
  height: 16px;
}

.rights-scrollbar::-webkit-scrollbar-track {
  background: rgba(4, 17, 26, 0.95);
  border-radius: 999px;
}

.rights-scrollbar::-webkit-scrollbar-thumb {
  background: linear-gradient(90deg, rgba(55, 242, 255, 0.55), rgba(123, 247, 255, 0.82));
  border-radius: 999px;
  border: 2px solid rgba(4, 17, 26, 0.95);
}

.rights-matrix-wrap {
  width: 100%;
  max-width: 100%;
  overflow-x: auto;
  overflow-y: auto;
  border-radius: 16px;
  border: 1px solid rgba(55, 242, 255, 0.18);
  background: rgba(2, 10, 16, 0.84);
  scrollbar-gutter: stable;
  scrollbar-color: rgba(55, 242, 255, 0.72) rgba(4, 17, 26, 0.95);
  scrollbar-width: auto;
}

.rights-matrix-wrap::-webkit-scrollbar {
  height: 16px;
  width: 14px;
}

.rights-matrix-wrap::-webkit-scrollbar-track {
  background: rgba(4, 17, 26, 0.95);
  border-radius: 999px;
}

.rights-matrix-wrap::-webkit-scrollbar-thumb {
  background: linear-gradient(90deg, rgba(55, 242, 255, 0.55), rgba(123, 247, 255, 0.82));
  border-radius: 999px;
  border: 2px solid rgba(4, 17, 26, 0.95);
}

.rights-matrix {
  width: max-content;
  min-width: 100%;
  border-collapse: separate;
  border-spacing: 0;
}

.rights-matrix thead th {
  position: sticky;
  top: 0;
  z-index: 2;
  background: rgba(1, 11, 18, 0.96);
  border-bottom: 1px solid rgba(55, 242, 255, 0.18);
  padding: 14px 12px;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  font-size: 10px;
  color: rgba(209, 251, 255, 0.68);
}

.rights-col-member {
  left: 0;
  z-index: 4;
  min-width: 320px;
  width: 320px;
  position: sticky;
}

.rights-col-role {
  left: 320px;
  z-index: 4;
  min-width: 172px;
  width: 172px;
  position: sticky;
}

.rights-col-operation {
  min-width: 132px;
  width: 132px;
  text-align: center;
}

.rights-op-label {
  color: rgba(229, 252, 255, 0.92);
}

.rights-op-code {
  margin-top: 5px;
  color: rgba(136, 232, 255, 0.58);
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: none;
}

.rights-member-cell,
.rights-role-cell {
  position: sticky;
  background: rgba(1, 9, 15, 0.96);
  z-index: 1;
}

.rights-member-cell {
  left: 0;
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 320px;
  width: 320px;
  padding: 18px 14px;
  border-right: 1px solid rgba(55, 242, 255, 0.12);
}

.rights-role-cell {
  left: 320px;
  min-width: 172px;
  width: 172px;
  padding: 14px 12px;
  border-right: 1px solid rgba(55, 242, 255, 0.12);
}

.rights-matrix tbody tr + tr td {
  border-top: 1px solid rgba(55, 242, 255, 0.08);
}

.rights-member-avatar {
  width: 38px;
  height: 38px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  border: 1px solid rgba(55, 242, 255, 0.28);
  background: rgba(0, 119, 160, 0.2);
  color: #37f2ff;
  font-size: 15px;
  font-weight: 700;
  letter-spacing: 0.1em;
}

.rights-member-copy {
  display: grid;
  gap: 6px;
}

.rights-member-name {
  color: #e8feff;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  font-size: 15px;
}

.rights-member-secondary {
  color: rgba(188, 246, 255, 0.72);
  font-size: 11px;
}

.rights-member-meta {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.rights-role-select {
  width: 100%;
  border: 1px solid rgba(55, 242, 255, 0.24);
  border-radius: 10px;
  background: rgba(5, 21, 34, 0.94);
  color: #e1fcff;
  padding: 9px 10px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-size: 11px;
}

.rights-cell-shell {
  padding: 16px 12px;
  text-align: center;
}

.rights-cell {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  border: 1px solid rgba(55, 242, 255, 0.22);
  background: rgba(1, 12, 19, 0.86);
  color: transparent;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.16s ease, border-color 0.16s ease, box-shadow 0.16s ease, background 0.16s ease;
}

.rights-cell:hover {
  transform: translateY(-1px);
  border-color: rgba(55, 242, 255, 0.4);
}

.rights-cell-indicator {
  font-size: 14px;
  line-height: 1;
}

.rights-cell.is-enabled {
  color: rgba(232, 254, 255, 0.98);
}

.rights-cell.is-role {
  background: rgba(18, 143, 188, 0.22);
  border-color: rgba(55, 242, 255, 0.38);
  box-shadow: inset 0 0 0 1px rgba(55, 242, 255, 0.12);
}

.rights-cell.is-grant {
  background: rgba(35, 224, 255, 0.28);
  border-color: rgba(103, 247, 255, 0.58);
  box-shadow: 0 0 16px rgba(55, 242, 255, 0.16);
}

.rights-cell.is-deny {
  border-color: rgba(255, 166, 85, 0.48);
  background: rgba(58, 29, 5, 0.72);
  color: rgba(255, 181, 109, 0.94);
}

.rights-cell.is-draft {
  box-shadow: 0 0 0 1px rgba(255, 179, 92, 0.32), 0 0 18px rgba(255, 179, 92, 0.12);
}

.rights-cell.is-disabled {
  color: transparent;
}

.mono {
  font-family: "JetBrains Mono", "Cascadia Mono", monospace;
}

@media (max-width: 1280px) {
  .rights-toolbar {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 900px) {
  .rights-toolbar {
    grid-template-columns: 1fr;
  }

  .rights-actions {
    flex-direction: column;
    align-items: stretch;
  }

  .rights-action-buttons {
    justify-content: flex-start;
  }
}
</style>
