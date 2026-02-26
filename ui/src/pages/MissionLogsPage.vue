<template>
  <div class="legacy-mission-route-redirect">
    <div class="registry-shell">
      <section class="panel registry-main">
        <div class="panel-header">
          <div>
            <div class="panel-title">Mission Logbook Redirect</div>
            <div class="panel-subtitle">Routing to canonical mission-domain log-entry page...</div>
          </div>
        </div>
        <p class="panel-empty">Redirecting...</p>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from "vue";
import { useRoute } from "vue-router";
import { useRouter } from "vue-router";

const route = useRoute();
const router = useRouter();

const queryText = (value: unknown): string => {
  if (Array.isArray(value)) {
    return String(value[0] ?? "").trim();
  }
  return String(value ?? "").trim();
};

onMounted(() => {
  const missionUid = queryText(route.query.mission_uid);
  if (!missionUid) {
    router.push({ path: "/missions", query: route.query }).catch(() => undefined);
    return;
  }
  const nextQuery = { ...route.query, mission_uid: missionUid };
  router
    .replace({ path: `/missions/${encodeURIComponent(missionUid)}/log-entries`, query: nextQuery })
    .catch(() => undefined);
});
</script>
