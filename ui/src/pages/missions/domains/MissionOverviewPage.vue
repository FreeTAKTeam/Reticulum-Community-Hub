<template>
  <section class="panel registry-main mission-overview-page">
    <div class="panel-header">
      <div>
        <div class="panel-title">Mission Overview</div>
        <div class="panel-subtitle">Read-only mission KPI composition across domain objects</div>
      </div>
      <div class="panel-chip">{{ selectedMissionUid || "No mission" }}</div>
    </div>

    <div class="mission-kpis">
      <article class="kpi-card">
        <span class="kpi-label">Checklists</span>
        <strong class="kpi-value">{{ workspace.missionScopedChecklists.length }}</strong>
      </article>
      <article class="kpi-card">
        <span class="kpi-label">Teams</span>
        <strong class="kpi-value">{{ workspace.missionScopedTeamUids.size }}</strong>
      </article>
      <article class="kpi-card">
        <span class="kpi-label">Members</span>
        <strong class="kpi-value">{{ workspace.missionScopedMembers.length }}</strong>
      </article>
      <article class="kpi-card">
        <span class="kpi-label">Assets</span>
        <strong class="kpi-value">{{ workspace.missionScopedAssets.length }}</strong>
      </article>
      <article class="kpi-card">
        <span class="kpi-label">Assignments</span>
        <strong class="kpi-value">{{ workspace.missionScopedAssignments.length }}</strong>
      </article>
      <article class="kpi-card">
        <span class="kpi-label">Zones</span>
        <strong class="kpi-value">{{ workspace.missionScopedZones.length }}</strong>
      </article>
    </div>

    <ul class="stack-list" v-if="workspace.selectedMission">
      <li>
        <strong>Mission Name</strong>
        <span>{{ workspace.selectedMission.mission_name || workspace.selectedMission.uid }}</span>
      </li>
      <li>
        <strong>Status</strong>
        <span class="mission-status-chip" :class="missionStatusChipClass(workspace.selectedMission.mission_status)">
          {{ missionStatusLabel(workspace.selectedMission.mission_status) }}
        </span>
      </li>
      <li>
        <strong>Topic</strong>
        <span>{{ workspace.selectedMission.topic_id || "-" }}</span>
      </li>
      <li>
        <strong>Description</strong>
        <span>{{ workspace.selectedMission.description || "-" }}</span>
      </li>
      <li>
        <strong>Expiration</strong>
        <span>{{ workspace.selectedMission.expiration || "-" }}</span>
      </li>
    </ul>
    <div v-else class="panel-empty">No mission selected.</div>
  </section>
</template>

<script setup lang="ts">
import { onMounted } from "vue";
import { computed } from "vue";
import { watch } from "vue";
import { useRoute } from "vue-router";
import { getMissionStatusLabel } from "../mission-status";
import { getMissionStatusTone } from "../mission-status";
import { useMissionWorkspaceStore } from "../../../stores/missionWorkspace";
import { toMissionUidFromRouteParam } from "../../../types/missions/routes";

const route = useRoute();
const workspace = useMissionWorkspaceStore();
const missionStatusLabel = (value?: string | null): string => getMissionStatusLabel(value);
const missionStatusChipClass = (value?: string | null): string => `mission-status-chip--${getMissionStatusTone(value)}`;

const selectedMissionUid = computed(() => toMissionUidFromRouteParam(route.params.mission_uid));

watch(
  () => route.params.mission_uid,
  (value) => {
    workspace.setSelectedMissionUid(toMissionUidFromRouteParam(value));
  },
  { immediate: true }
);

onMounted(() => {
  if (!workspace.missions.length && !workspace.loading) {
    workspace.loadWorkspace().catch(() => undefined);
  }
});
</script>

<style scoped>
.mission-overview-page {
  min-height: 340px;
}

.mission-status-chip {
  display: inline-flex;
  align-items: center;
  border: 1px solid rgb(var(--CosmicUI-Secondary-rgb) / 45%);
  border-radius: 999px;
  padding: 2px 8px;
  font-size: 10px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  background: var(--cui-mission-status-chip-background);
  color: rgb(var(--CosmicUI-Secondary-rgb) / 92%);
}

.mission-status-chip--active {
  border-color: var(--cui-mission-status-active);
  color: var(--cui-mission-status-active-text);
  box-shadow: 0 0 12px var(--cui-mission-status-active-glow);
}

.mission-status-chip--pending {
  border-color: var(--cui-mission-status-pending);
  color: var(--cui-mission-status-pending-text);
  box-shadow: 0 0 12px var(--cui-mission-status-pending-glow);
}

.mission-status-chip--success {
  border-color: var(--cui-mission-status-success);
  color: var(--cui-mission-status-success-text);
  box-shadow: 0 0 12px var(--cui-mission-status-success-glow);
}

.mission-status-chip--failed {
  border-color: var(--cui-mission-status-failed);
  color: var(--cui-mission-status-failed-text);
  box-shadow: 0 0 12px var(--cui-mission-status-failed-glow);
}

.mission-status-chip--deleted {
  border-color: var(--cui-mission-status-deleted);
  color: var(--cui-mission-status-deleted-text);
  box-shadow: 0 0 12px var(--cui-mission-status-deleted-glow);
}
</style>
