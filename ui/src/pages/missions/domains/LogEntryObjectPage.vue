<template>
  <LogEntryObjectLegacyPage />
</template>

<script setup lang="ts">
import { onMounted } from "vue";
import { watch } from "vue";
import { useRoute } from "vue-router";
import { useRouter } from "vue-router";
import LogEntryObjectLegacyPage from "./LogEntryObjectLegacyPage.vue";
import { toMissionUidFromRouteParam } from "../../../types/missions/routes";

const route = useRoute();
const router = useRouter();

const syncMissionUidQuery = () => {
  const missionUid = toMissionUidFromRouteParam(route.params.mission_uid);
  const current = Array.isArray(route.query.mission_uid)
    ? String(route.query.mission_uid[0] ?? "").trim()
    : String(route.query.mission_uid ?? "").trim();
  if (!missionUid || current === missionUid) {
    return;
  }
  router.replace({ path: route.path, query: { ...route.query, mission_uid: missionUid } }).catch(() => undefined);
};

watch(
  () => route.params.mission_uid,
  () => {
    syncMissionUidQuery();
  },
  { immediate: true }
);

onMounted(() => {
  syncMissionUidQuery();
});
</script>
