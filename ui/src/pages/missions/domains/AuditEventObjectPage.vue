<template>
  <section class="panel registry-main">
    <div class="panel-header">
      <div>
        <div class="panel-title">Audit Event</div>
        <div class="panel-subtitle">Derived timeline merged from events, mission changes, and log entries</div>
      </div>
      <div class="panel-chip">{{ timelineRows.length }} records</div>
    </div>

    <div class="domain-actions">
      <BaseButton size="sm" variant="secondary" icon-left="refresh" :disabled="workspace.loading" @click="reload">
        Refresh
      </BaseButton>
      <BaseButton size="sm" icon-left="layers" @click="openLegacyWorkspace">Open Legacy Logbook</BaseButton>
    </div>

    <div v-if="workspace.loading" class="panel-empty">Loading audit timeline...</div>
    <div v-else-if="!timelineRows.length" class="panel-empty">No audit events for this mission scope.</div>
    <div v-else class="table-wrap cui-scrollbar">
      <table class="mini-table">
        <thead>
          <tr>
            <th>Timestamp</th>
            <th>Source</th>
            <th>Type</th>
            <th>Message</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in timelineRows" :key="row.id">
            <td>{{ row.timestamp || "-" }}</td>
            <td>{{ row.source }}</td>
            <td>{{ row.type }}</td>
            <td>{{ row.message }}</td>
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

interface TimelineRow {
  id: string;
  timestamp: string;
  source: "event" | "mission_change" | "log_entry";
  type: string;
  message: string;
  epoch: number;
}

const route = useRoute();
const router = useRouter();
const workspace = useMissionWorkspaceStore();

const missionUid = computed(() => toMissionUidFromRouteParam(route.params.mission_uid));

const toEpoch = (value: string): number => {
  const epoch = Date.parse(value || "");
  return Number.isNaN(epoch) ? 0 : epoch;
};

const timelineRows = computed<TimelineRow[]>(() => {
  const selectedMissionUid = missionUid.value;

  const fromEvents = workspace.events
    .filter((entry) => {
      const aggregateUid = String(entry.aggregate_uid ?? "").trim();
      if (aggregateUid === selectedMissionUid) {
        return true;
      }
      const payloadText = JSON.stringify(entry.payload ?? "");
      return payloadText.includes(selectedMissionUid);
    })
    .map((entry, index) => {
      const timestamp = String(entry.created_at ?? "").trim();
      const type = String(entry.event_type ?? "domain.event").trim();
      return {
        id: `event-${String(entry.event_uid ?? index)}`,
        timestamp,
        source: "event" as const,
        type,
        message: `Aggregate ${String(entry.aggregate_type ?? "-")} / ${String(entry.aggregate_uid ?? "-")}`,
        epoch: toEpoch(timestamp)
      };
    });

  const fromMissionChanges = workspace.missionChanges
    .filter((entry) => String(entry.mission_uid ?? "").trim() === selectedMissionUid)
    .map((entry, index) => {
      const timestamp = String(entry.timestamp ?? "").trim();
      const title = String(entry.name ?? "Mission change").trim();
      const notes = String(entry.notes ?? "").trim();
      return {
        id: `mission-change-${String(entry.uid ?? index)}`,
        timestamp,
        source: "mission_change" as const,
        type: String(entry.change_type ?? "MISSION_CHANGE").trim() || "MISSION_CHANGE",
        message: notes ? `${title}: ${notes}` : title,
        epoch: toEpoch(timestamp)
      };
    });

  const fromLogEntries = workspace.logEntries
    .filter((entry) => String(entry.mission_uid ?? "").trim() === selectedMissionUid)
    .map((entry, index) => {
      const timestamp =
        String(entry.server_time ?? "").trim() ||
        String(entry.client_time ?? "").trim() ||
        String(entry.created_at ?? "").trim();
      const content = String(entry.content ?? "").trim();
      return {
        id: `log-entry-${String(entry.entry_uid ?? index)}`,
        timestamp,
        source: "log_entry" as const,
        type: "MISSION_LOG_ENTRY",
        message: content || "Mission log entry",
        epoch: toEpoch(timestamp)
      };
    });

  return [...fromEvents, ...fromMissionChanges, ...fromLogEntries].sort((left, right) => right.epoch - left.epoch);
});

const reload = async () => {
  await workspace.loadWorkspace();
};

const openLegacyWorkspace = () => {
  const selectedMissionUid = missionUid.value;
  router
    .push({
      path: "/missions/logs",
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
