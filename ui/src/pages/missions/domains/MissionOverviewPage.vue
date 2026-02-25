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
        <span>{{ workspace.selectedMission.mission_status || "UNSCOPED" }}</span>
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
import { useRoute } from "vue-router";
import { useMissionWorkspaceStore } from "../../../stores/missionWorkspace";
import { toMissionUidFromRouteParam } from "../../../types/missions/routes";

const route = useRoute();
const workspace = useMissionWorkspaceStore();

const selectedMissionUid = computed(() => toMissionUidFromRouteParam(route.params.mission_uid));

onMounted(() => {
  workspace.setSelectedMissionUid(selectedMissionUid.value);
  if (!workspace.missions.length && !workspace.loading) {
    workspace.loadWorkspace().catch(() => undefined);
  }
});
</script>

<style scoped>
.mission-overview-page {
  min-height: 340px;
}
</style>
