<template>
  <div class="missions-cutover-redirect registry-shell">
    <section class="panel registry-main">
      <div class="panel-header">
        <div>
          <div class="panel-title">Mission Workspace Redirect</div>
          <div class="panel-subtitle">Routing to canonical mission-domain workspace...</div>
        </div>
      </div>
      <div v-if="errorMessage" class="panel-empty">
        {{ errorMessage }}
      </div>
      <div v-else class="panel-empty">Redirecting...</div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from "vue";
import { ref } from "vue";
import { useRoute } from "vue-router";
import { useRouter } from "vue-router";
import { useMissionWorkspaceStore } from "../stores/missionWorkspace";
import { MISSION_DOMAIN_ROUTE_NAMES } from "../types/missions/routes";

const route = useRoute();
const router = useRouter();
const workspace = useMissionWorkspaceStore();

const errorMessage = ref("");

const queryText = (value: unknown): string => {
  if (Array.isArray(value)) {
    return String(value[0] ?? "").trim();
  }
  return String(value ?? "").trim();
};

const isLegacyRequested = (): boolean => {
  const legacy = queryText(route.query.legacy).toLowerCase();
  const mode = queryText(route.query.mode).toLowerCase();
  return legacy === "1" || legacy === "true" || mode === "legacy";
};

const redirectToCanonicalWorkspace = async () => {
  try {
    if (isLegacyRequested()) {
      await router.replace({ path: "/missions/legacy", query: route.query });
      return;
    }

    workspace.restorePersistedSelection();

    const queryMissionUid = queryText(route.query.mission_uid);
    let missionUid = queryMissionUid || workspace.selectedMissionUid;

    if (!missionUid) {
      if (!workspace.missions.length && !workspace.loading) {
        await workspace.loadWorkspace();
      }
      missionUid = queryMissionUid || workspace.selectedMissionUid || String(workspace.missions[0]?.uid ?? "").trim();
    }

    if (!missionUid) {
      await router.replace({ path: "/missions/legacy", query: { ...route.query, empty: "1" } });
      return;
    }

    workspace.setSelectedMissionUid(missionUid);

    await router.replace({
      name: MISSION_DOMAIN_ROUTE_NAMES.overview,
      params: { mission_uid: missionUid },
      query: { ...route.query, mission_uid: missionUid }
    });
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "Unable to resolve mission workspace route";
  }
};

onMounted(() => {
  redirectToCanonicalWorkspace().catch(() => undefined);
});
</script>
