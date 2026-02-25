<template>
  <div class="missions-workspace">
    <div class="registry-shell">
      <CosmicTopStatus title="Mission Domain Workspace" />

      <section class="mission-kpis">
        <article class="kpi-card">
          <span class="kpi-label">Missions</span>
          <strong class="kpi-value">{{ workspace.missions.length }}</strong>
        </article>
        <article class="kpi-card">
          <span class="kpi-label">Checklists</span>
          <strong class="kpi-value">{{ workspace.checklists.length }}</strong>
        </article>
        <article class="kpi-card">
          <span class="kpi-label">Assets</span>
          <strong class="kpi-value">{{ workspace.assets.length }}</strong>
        </article>
        <article class="kpi-card">
          <span class="kpi-label">Events</span>
          <strong class="kpi-value">{{ workspace.events.length }}</strong>
        </article>
      </section>

      <div class="registry-grid">
        <aside class="panel registry-tree">
          <div class="panel-header">
            <div>
              <div class="panel-title">Mission Directory</div>
              <div class="panel-subtitle">Select Mission Scope</div>
            </div>
            <div class="panel-chip">{{ workspace.missions.length }} records</div>
          </div>

          <div class="tree-list">
            <button
              v-for="mission in workspace.missions"
              :key="String(mission.uid)"
              class="tree-item"
              :class="{ active: selectedMissionUid === String(mission.uid ?? '').trim() }"
              type="button"
              @click="selectMission(String(mission.uid ?? '').trim())"
            >
              <span class="tree-dot" aria-hidden="true"></span>
              <span class="tree-label">{{ mission.mission_name || mission.uid }}</span>
              <span class="tree-count">{{ mission.mission_status || "UNKNOWN" }}</span>
            </button>
          </div>

          <div class="mission-directory-actions">
            <BaseButton size="sm" variant="secondary" icon-left="refresh" :disabled="workspace.loading" @click="reloadWorkspace">
              Refresh
            </BaseButton>
            <BaseButton size="sm" icon-left="layers" @click="openLegacyMissions">
              Legacy Workspace
            </BaseButton>
          </div>
        </aside>

        <section class="panel registry-main">
          <div class="panel-header">
            <div>
              <div class="panel-title">Domain Objects</div>
              <div class="panel-subtitle">Canonical /missions/:mission_uid/* routes</div>
            </div>
            <div class="panel-chip">{{ selectedMissionUid || "No mission" }}</div>
          </div>

          <div class="domain-tab-grid">
            <RouterLink
              v-for="item in domainNav"
              :key="item.name"
              :to="domainLink(item.name)"
              class="panel-tab"
              :class="{ active: route.name === item.name }"
            >
              {{ item.label }}
            </RouterLink>
          </div>

          <RouterView />
        </section>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { onMounted } from "vue";
import { watch } from "vue";
import { useRoute } from "vue-router";
import { useRouter } from "vue-router";
import BaseButton from "../../components/BaseButton.vue";
import CosmicTopStatus from "../../components/cosmic/CosmicTopStatus.vue";
import { useMissionScope } from "../../composables/missions/useMissionScope";
import { useMissionWorkspaceStore } from "../../stores/missionWorkspace";
import { MISSION_DOMAIN_ROUTE_NAMES } from "../../types/missions/routes";
import { toMissionUidFromRouteParam } from "../../types/missions/routes";

const route = useRoute();
const router = useRouter();
const workspace = useMissionWorkspaceStore();
const { selectedMissionUid } = useMissionScope();

const domainNav = [
  { name: MISSION_DOMAIN_ROUTE_NAMES.overview, label: "Overview" },
  { name: MISSION_DOMAIN_ROUTE_NAMES.mission, label: "Mission" },
  { name: MISSION_DOMAIN_ROUTE_NAMES.topic, label: "Topic" },
  { name: MISSION_DOMAIN_ROUTE_NAMES.checklist, label: "Checklist" },
  { name: MISSION_DOMAIN_ROUTE_NAMES.checklistTask, label: "Checklist Task" },
  { name: MISSION_DOMAIN_ROUTE_NAMES.checklistTemplate, label: "Checklist Template" },
  { name: MISSION_DOMAIN_ROUTE_NAMES.team, label: "Team" },
  { name: MISSION_DOMAIN_ROUTE_NAMES.teamMember, label: "Team Member" },
  { name: MISSION_DOMAIN_ROUTE_NAMES.skill, label: "Skill" },
  { name: MISSION_DOMAIN_ROUTE_NAMES.teamMemberSkill, label: "Team Member Skill" },
  { name: MISSION_DOMAIN_ROUTE_NAMES.taskSkillRequirement, label: "Task Skill Requirement" },
  { name: MISSION_DOMAIN_ROUTE_NAMES.asset, label: "Asset" },
  { name: MISSION_DOMAIN_ROUTE_NAMES.assignment, label: "Assignment" },
  { name: MISSION_DOMAIN_ROUTE_NAMES.zone, label: "Zone" },
  { name: MISSION_DOMAIN_ROUTE_NAMES.domainEvent, label: "Domain Event" },
  { name: MISSION_DOMAIN_ROUTE_NAMES.missionChange, label: "Mission Change" },
  { name: MISSION_DOMAIN_ROUTE_NAMES.logEntry, label: "Log Entry" },
  { name: MISSION_DOMAIN_ROUTE_NAMES.snapshot, label: "Snapshot" },
  { name: MISSION_DOMAIN_ROUTE_NAMES.auditEvent, label: "Audit Event" }
] as const;

const activeMissionUid = computed(() => {
  if (selectedMissionUid.value) {
    return selectedMissionUid.value;
  }
  return String(workspace.missions[0]?.uid ?? "").trim();
});

const domainLink = (name: string) => ({
  name,
  params: {
    mission_uid: activeMissionUid.value
  },
  query: activeMissionUid.value ? { mission_uid: activeMissionUid.value } : undefined
});

const selectMission = (missionUid: string) => {
  const nextMissionUid = missionUid.trim();
  if (!nextMissionUid) {
    return;
  }
  selectedMissionUid.value = nextMissionUid;
  const currentName = typeof route.name === "string" ? route.name : MISSION_DOMAIN_ROUTE_NAMES.overview;
  const targetName = currentName.startsWith("mission-domain-")
    ? currentName
    : MISSION_DOMAIN_ROUTE_NAMES.overview;
  router
    .push({
      name: targetName,
      params: { mission_uid: nextMissionUid },
      query: { ...route.query, mission_uid: nextMissionUid }
    })
    .catch(() => undefined);
};

const reloadWorkspace = async () => {
  await workspace.loadWorkspace();
};

const openLegacyMissions = () => {
  const missionUid = activeMissionUid.value;
  router
    .push({
      path: "/missions",
      query: missionUid ? { mission_uid: missionUid } : undefined
    })
    .catch(() => undefined);
};

watch(
  () => route.params.mission_uid,
  (value) => {
    const missionUid = toMissionUidFromRouteParam(value);
    if (missionUid && missionUid !== selectedMissionUid.value) {
      selectedMissionUid.value = missionUid;
    }
  },
  { immediate: true }
);

onMounted(() => {
  if (!workspace.missions.length && !workspace.loading) {
    workspace.loadWorkspace().catch(() => undefined);
  }
});
</script>

<style scoped src="./MissionsPage.css"></style>

<style scoped>
.domain-tab-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}
</style>
