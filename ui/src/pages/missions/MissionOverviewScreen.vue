<template>
  <div class="mission-overview-hud">
    <section class="overview-vitals">
      <article class="overview-vital-card">
        <span class="overview-vital-label">Mission Status</span>
        <strong class="overview-vital-value">{{ missionStatus || "UNSCOPED" }}</strong>
      </article>
      <article class="overview-vital-card">
        <span class="overview-vital-label">Checklist Runs</span>
        <strong class="overview-vital-value">{{ checklistRuns }}</strong>
      </article>
      <article class="overview-vital-card">
        <span class="overview-vital-label">Open Tasks</span>
        <strong class="overview-vital-value">{{ openTasks }}</strong>
      </article>
      <article class="overview-vital-card">
        <span class="overview-vital-label">Team Members</span>
        <strong class="overview-vital-value">{{ teamMembers }}</strong>
      </article>
      <article class="overview-vital-card">
        <span class="overview-vital-label">Assigned Assets</span>
        <strong class="overview-vital-value">{{ assignedAssets }}</strong>
      </article>
      <article class="overview-vital-card">
        <span class="overview-vital-label">Assigned Zones</span>
        <strong class="overview-vital-value">{{ assignedZones }}</strong>
      </article>
    </section>

    <section class="overview-layout">
      <article class="stage-card overview-panel overview-panel-compact">
        <div class="overview-compact-header">
          <div>
            <h4>Mission Profile</h4>
            <div class="overview-compact-subtitle mono">
              {{ missionUid || "No mission selected" }}
            </div>
          </div>
          <span class="overview-compact-tag">{{ missionStatus || "UNSCOPED" }}</span>
        </div>
        <div class="overview-compact-meta">
          <div>
            <span>Topic</span>
            <span>{{ missionTopicName }}</span>
          </div>
          <div>
            <span>Description</span>
            <span class="overview-compact-truncate" :title="missionDescription || '-'">
              {{ missionDescription || "-" }}
            </span>
          </div>
        </div>
      </article>

      <article class="stage-card overview-panel overview-panel-compact">
        <div class="overview-compact-header">
          <div>
            <h4>Mission Excheck Snapshot</h4>
            <div class="overview-compact-subtitle">Condensed lane status</div>
          </div>
          <span class="overview-compact-tag">{{ missionTotalTasks }} Tasks</span>
        </div>
        <div class="overview-board overview-board-compact">
          <div class="overview-board-col overview-board-col-pending">
            <div class="overview-board-col-head">
              <h5>Pending</h5>
              <span>{{ boardCounts.pending }}</span>
            </div>
            <ul class="lane-list lane-list-compact">
              <li v-for="task in boardLaneTasks.pending.slice(0, 3)" :key="`overview-pending-${task.id}`">
                <strong>{{ task.name }}</strong>
                <span>{{ task.meta }}</span>
              </li>
              <li v-if="!boardLaneTasks.pending.length" class="lane-empty">No pending tasks.</li>
            </ul>
          </div>
          <div class="overview-board-col overview-board-col-late">
            <div class="overview-board-col-head">
              <h5>Late</h5>
              <span>{{ boardCounts.late }}</span>
            </div>
            <ul class="lane-list lane-list-compact">
              <li v-for="task in boardLaneTasks.late.slice(0, 3)" :key="`overview-late-${task.id}`">
                <strong>{{ task.name }}</strong>
                <span>{{ task.meta }}</span>
              </li>
              <li v-if="!boardLaneTasks.late.length" class="lane-empty">No late tasks.</li>
            </ul>
          </div>
          <div class="overview-board-col overview-board-col-complete">
            <div class="overview-board-col-head">
              <h5>Complete</h5>
              <span>{{ boardCounts.complete }}</span>
            </div>
            <ul class="lane-list lane-list-compact">
              <li v-for="task in boardLaneTasks.complete.slice(0, 3)" :key="`overview-complete-${task.id}`">
                <strong>{{ task.name }}</strong>
                <span>{{ task.meta }}</span>
              </li>
              <li v-if="!boardLaneTasks.complete.length" class="lane-empty">No completed tasks.</li>
            </ul>
          </div>
        </div>
      </article>

      <article class="stage-card overview-panel overview-panel-wide">
        <div class="mission-audit-head">
          <div>
            <h4>Mission Activity / Audit</h4>
            <span class="mission-audit-subtitle">
              Unified mission activity stream (events + mission changes + log entries)
            </span>
          </div>
          <span class="overview-panel-meta">Latest {{ missionAudit.length }} entries</span>
        </div>
        <div class="mission-audit-actions">
          <BaseButton size="sm" variant="secondary" icon-left="download" @click="emit('request-action', 'Export Log')">
            Export Log
          </BaseButton>
          <BaseButton size="sm" variant="secondary" icon-left="image" @click="emit('request-action', 'Snapshot')">
            Snapshot
          </BaseButton>
          <BaseButton size="sm" variant="secondary" icon-left="list" @click="emit('request-action', 'Open Logs')">
            Open Logs
          </BaseButton>
        </div>
        <div v-if="!missionAudit.length" class="mission-audit-empty">No mission activity yet.</div>
        <div v-else class="mission-audit-table-shell">
          <table class="mission-audit-table">
            <thead>
              <tr>
                <th>Event</th>
                <th>Type</th>
                <th>Time</th>
                <th class="mission-audit-cell-action">Details</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="event in missionAudit" :key="`mission-audit-${event.uid}`">
                <tr class="mission-audit-row">
                  <td class="mission-audit-cell-message">{{ event.message }}</td>
                  <td class="mission-audit-cell-type">
                    <span class="mission-audit-type-chip">{{ event.type }}</span>
                  </td>
                  <td class="mission-audit-cell-time">{{ formatAuditDateTime(event.timestamp) }}</td>
                  <td class="mission-audit-cell-action">
                    <button
                      type="button"
                      class="mission-audit-toggle"
                      :disabled="!hasMissionAuditDetails(event.details)"
                      @click="toggleMissionAuditExpanded(event.uid)"
                    >
                      {{ isMissionAuditExpanded(event.uid) ? "Hide" : "Details" }}
                    </button>
                  </td>
                </tr>
                <tr v-if="isMissionAuditExpanded(event.uid)" class="mission-audit-details-row">
                  <td colspan="4">
                    <div class="mission-audit-details">
                      <BaseFormattedOutput class="mission-audit-json" :value="event.details" />
                    </div>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
      </article>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from "vue";
import BaseButton from "../../components/BaseButton.vue";
import BaseFormattedOutput from "../../components/BaseFormattedOutput.vue";

interface OverviewBoardTask {
  id: string;
  name: string;
  meta: string;
}

interface MissionOverviewAuditEvent {
  uid: string;
  timestamp: string;
  type: string;
  message: string;
  details: Record<string, unknown> | null;
}

const props = defineProps<{
  missionStatus: string;
  checklistRuns: number;
  openTasks: number;
  teamMembers: number;
  assignedAssets: number;
  assignedZones: number;
  missionUid: string;
  missionTopicName: string;
  missionDescription: string;
  missionTotalTasks: number;
  boardCounts: {
    pending: number;
    late: number;
    complete: number;
  };
  boardLaneTasks: {
    pending: OverviewBoardTask[];
    late: OverviewBoardTask[];
    complete: OverviewBoardTask[];
  };
  missionAudit: MissionOverviewAuditEvent[];
}>();

const emit = defineEmits<{
  (event: "request-action", action: string): void;
}>();

const missionAuditExpandedRows = ref<Record<string, boolean>>({});

watch(
  () => props.missionUid,
  () => {
    missionAuditExpandedRows.value = {};
  }
);

watch(
  () => props.missionAudit,
  () => {
    missionAuditExpandedRows.value = {};
  }
);

const formatAuditDateTime = (value?: string | null): string => {
  if (!value) {
    return "--";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString();
};

const hasMissionAuditDetails = (value: Record<string, unknown> | null): boolean => {
  if (!value) {
    return false;
  }
  return Object.keys(value).length > 0;
};

const isMissionAuditExpanded = (uid: string): boolean => Boolean(missionAuditExpandedRows.value[uid]);

const toggleMissionAuditExpanded = (uid: string): void => {
  const current = missionAuditExpandedRows.value;
  missionAuditExpandedRows.value = {
    ...current,
    [uid]: !current[uid]
  };
};
</script>

<style scoped src="./MissionOverviewScreen.css"></style>
