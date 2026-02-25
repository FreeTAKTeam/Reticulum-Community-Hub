<template>
  <section class="panel registry-main">
    <div class="panel-header">
      <div>
        <div class="panel-title">Checklist Task</div>
        <div class="panel-subtitle">Flattened task rows for mission-scoped checklists</div>
      </div>
      <div class="panel-chip">{{ rows.length }} records</div>
    </div>

    <div class="domain-actions">
      <BaseButton size="sm" variant="secondary" icon-left="refresh" :disabled="workspace.loading" @click="reload">
        Refresh
      </BaseButton>
      <BaseButton size="sm" icon-left="layers" @click="openLegacyWorkspace">Open Checklist Workspace</BaseButton>
    </div>

    <div v-if="workspace.loading" class="panel-empty">Loading checklist tasks...</div>
    <div v-else-if="!rows.length" class="panel-empty">No checklist task rows in this mission scope.</div>
    <div v-else class="table-wrap cui-scrollbar">
      <table class="mini-table">
        <thead>
          <tr>
            <th>Checklist</th>
            <th>Task UID</th>
            <th>#</th>
            <th>Status</th>
            <th>Due DTG</th>
            <th>Due Relative (min)</th>
            <th>Completed At</th>
            <th>Assignee</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.id">
            <td>{{ row.checklist }}</td>
            <td>{{ row.task_uid }}</td>
            <td>{{ row.number }}</td>
            <td>{{ row.status }}</td>
            <td>{{ row.due_dtg || "-" }}</td>
            <td>{{ row.due_relative_minutes === null ? "-" : row.due_relative_minutes }}</td>
            <td>{{ row.completed_at || "-" }}</td>
            <td>{{ row.assignee || "-" }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { onMounted } from "vue";
import { useRoute } from "vue-router";
import { useRouter } from "vue-router";
import BaseButton from "../../../components/BaseButton.vue";
import { useMissionWorkspaceStore } from "../../../stores/missionWorkspace";
import { toMissionUidFromRouteParam } from "../../../types/missions/routes";

const route = useRoute();
const router = useRouter();
const workspace = useMissionWorkspaceStore();

const missionUid = computed(() => toMissionUidFromRouteParam(route.params.mission_uid));

const rows = computed(() => {
  return workspace.missionScopedChecklists.flatMap((checklist) => {
    const checklistUid = String(checklist.uid ?? "").trim() || "-";
    const checklistName = String(checklist.name ?? checklistUid);
    const tasks = Array.isArray(checklist.tasks) ? checklist.tasks : [];
    return tasks.map((task) => ({
      id: `${checklistUid}-${String(task.task_uid ?? task.number ?? Math.random())}`,
      checklist: checklistName,
      task_uid: String(task.task_uid ?? "").trim() || "-",
      number: Number(task.number ?? 0),
      status: String(task.task_status ?? task.user_status ?? "PENDING").trim() || "PENDING",
      due_dtg: String(task.due_dtg ?? "").trim(),
      due_relative_minutes:
        task.due_relative_minutes === null || task.due_relative_minutes === undefined
          ? null
          : Number.isFinite(Number(task.due_relative_minutes))
            ? Math.trunc(Number(task.due_relative_minutes))
            : null,
      completed_at: String(task.completed_at ?? "").trim(),
      assignee: String(task.completed_by_team_member_rns_identity ?? "").trim()
    }));
  });
});

const reload = async () => {
  await workspace.loadWorkspace();
};

const openLegacyWorkspace = () => {
  const selectedMissionUid = missionUid.value;
  router
    .push({
      path: "/checklists",
      query: selectedMissionUid ? { mission_uid: selectedMissionUid } : undefined
    })
    .catch(() => undefined);
};

onMounted(() => {
  workspace.setSelectedMissionUid(missionUid.value);
  if (!workspace.missions.length && !workspace.loading) {
    workspace.loadWorkspace().catch(() => undefined);
  }
});
</script>

<style scoped>
.domain-actions {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}
</style>
