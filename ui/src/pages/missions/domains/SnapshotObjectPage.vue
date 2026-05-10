<template>
  <section class="panel registry-main">
    <div class="panel-header">
      <div>
        <div class="panel-title">Snapshot</div>
        <div class="panel-subtitle">Mission aggregate snapshots filtered by selected mission UID</div>
      </div>
      <div class="panel-chip">{{ snapshots.length }} records</div>
    </div>

    <div class="domain-actions">
      <BaseButton size="sm" variant="secondary" icon-left="refresh" :disabled="loading" @click="loadSnapshots">
        Refresh
      </BaseButton>
      <BaseButton size="sm" icon-left="layers" @click="openLegacyWorkspace">Open Legacy Workspace</BaseButton>
    </div>

    <div v-if="loading" class="panel-empty">Loading snapshots...</div>
    <div v-else-if="!snapshots.length" class="panel-empty">No snapshots for this mission.</div>
    <div v-else class="table-wrap cui-scrollbar">
      <table class="mini-table">
        <thead>
          <tr>
            <th>Aggregate UID</th>
            <th>Aggregate Type</th>
            <th>Created At</th>
            <th>State</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="snapshot in snapshots" :key="snapshot.id">
            <td>{{ snapshot.aggregate_uid }}</td>
            <td>{{ snapshot.aggregate_type }}</td>
            <td>{{ snapshot.created_at || "-" }}</td>
            <td>{{ snapshot.state }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted } from "vue";
import { computed } from "vue";
import { ref } from "vue";
import { useRoute } from "vue-router";
import { useRouter } from "vue-router";
import { get } from "../../../api/client";
import { endpoints } from "../../../api/endpoints";
import BaseButton from "../../../components/BaseButton.vue";
import { useMissionWorkspaceStore } from "../../../stores/missionWorkspace";
import { toMissionUidFromRouteParam } from "../../../types/missions/routes";

interface SnapshotRow {
  id: string;
  aggregate_uid: string;
  aggregate_type: string;
  created_at: string;
  state: string;
}

const route = useRoute();
const router = useRouter();
const workspace = useMissionWorkspaceStore();

const loading = ref(false);
const snapshots = ref<SnapshotRow[]>([]);

const missionUid = computed(() => toMissionUidFromRouteParam(route.params.mission_uid));

const stringifyState = (value: unknown): string => {
  try {
    const text = JSON.stringify(value);
    if (!text) {
      return "-";
    }
    return text.length > 120 ? `${text.slice(0, 120)}...` : text;
  } catch (_error) {
    return "[unserializable]";
  }
};

const loadSnapshots = async () => {
  loading.value = true;
  try {
    const payload = await get<Array<{ aggregate_uid?: string; aggregate_type?: string; state?: unknown; created_at?: string }>>(
      endpoints.r3aktSnapshots
    );
    const selectedMissionUid = missionUid.value;
    snapshots.value = payload
      .filter((entry) => String(entry.aggregate_uid ?? "").trim() === selectedMissionUid)
      .map((entry, index) => ({
        id: `${String(entry.aggregate_uid ?? "")}-${String(entry.created_at ?? "")}-${index}`,
        aggregate_uid: String(entry.aggregate_uid ?? "").trim(),
        aggregate_type: String(entry.aggregate_type ?? "").trim() || "-",
        created_at: String(entry.created_at ?? "").trim(),
        state: stringifyState(entry.state)
      }));
  } finally {
    loading.value = false;
  }
};

const openLegacyWorkspace = () => {
  const selectedMissionUid = missionUid.value;
  router
    .push({
      path: "/missions",
      query: selectedMissionUid ? { mission_uid: selectedMissionUid, screen: "missionOverview" } : undefined
    })
    .catch(() => undefined);
};

onMounted(() => {
  workspace.setSelectedMissionUid(missionUid.value);
  loadSnapshots().catch(() => undefined);
});
</script>

<style scoped>
.domain-actions {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}
</style>
