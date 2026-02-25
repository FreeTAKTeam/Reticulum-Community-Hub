<template>
  <section class="panel registry-main mission-domain-record-page">
    <div class="panel-header">
      <div>
        <div class="panel-title">{{ title }}</div>
        <div class="panel-subtitle">{{ subtitle }}</div>
      </div>
      <div class="panel-chip">{{ scopedRows.length }} records</div>
    </div>

    <div class="domain-actions">
      <BaseButton size="sm" variant="secondary" icon-left="refresh" :disabled="workspace.loading" @click="reload">
        Refresh
      </BaseButton>
      <BaseButton size="sm" icon-left="layers" @click="openLegacyWorkspace">
        Open Legacy Workspace
      </BaseButton>
    </div>

    <div v-if="workspace.loading" class="panel-empty">Loading {{ title.toLowerCase() }}...</div>
    <div v-else-if="!scopedRows.length" class="panel-empty">No {{ title.toLowerCase() }} records for this mission scope.</div>
    <div v-else class="table-wrap cui-scrollbar">
      <table class="mini-table">
        <thead>
          <tr>
            <th v-for="column in columnKeys" :key="`${title}-column-${column}`">{{ prettyColumn(column) }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, rowIndex) in visibleRows" :key="rowKey(row, rowIndex)">
            <td v-for="column in columnKeys" :key="`${title}-cell-${rowIndex}-${column}`">{{ formatCell(row[column]) }}</td>
          </tr>
        </tbody>
      </table>
      <p v-if="scopedRows.length > visibleRows.length" class="domain-truncate-note">
        Showing {{ visibleRows.length }} of {{ scopedRows.length }} rows.
      </p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { onMounted } from "vue";
import { useRoute } from "vue-router";
import { useRouter } from "vue-router";
import BaseButton from "../../../components/BaseButton.vue";
import type { MissionWorkspaceCollectionKey } from "../../../stores/missionWorkspace";
import { useMissionWorkspaceStore } from "../../../stores/missionWorkspace";
import { toMissionUidFromRouteParam } from "../../../types/missions/routes";

interface Props {
  title: string;
  subtitle: string;
  collectionKey: MissionWorkspaceCollectionKey;
  legacyPath?: string;
  legacyScreen?: string;
}

const props = withDefaults(defineProps<Props>(), {
  legacyPath: "/missions",
  legacyScreen: ""
});

const route = useRoute();
const router = useRouter();
const workspace = useMissionWorkspaceStore();

const missionUid = computed(() => toMissionUidFromRouteParam(route.params.mission_uid));

const recordsByKey = computed(() => {
  switch (props.collectionKey) {
    case "missions": {
      const selectedMissionUid = missionUid.value;
      return workspace.missions.filter((entry) => String(entry.uid ?? "").trim() === selectedMissionUid);
    }
    case "checklists":
      return workspace.missionScopedChecklists;
    case "teams":
      return workspace.teams.filter((entry) => {
        const selectedMissionUid = missionUid.value;
        const missionUids = [
          ...((Array.isArray(entry.mission_uids) ? entry.mission_uids : []).map((item) => String(item ?? "").trim())),
          String(entry.mission_uid ?? "").trim()
        ];
        return missionUids.includes(selectedMissionUid);
      });
    case "members":
      return workspace.missionScopedMembers;
    case "assets":
      return workspace.missionScopedAssets;
    case "assignments":
      return workspace.missionScopedAssignments;
    case "zones":
      return workspace.missionScopedZones;
    case "events":
      return workspace.events.filter((entry) => {
        const selectedMissionUid = missionUid.value;
        const aggregateUid = String(entry.aggregate_uid ?? "").trim();
        if (aggregateUid === selectedMissionUid) {
          return true;
        }
        const payloadText = JSON.stringify(entry.payload ?? "");
        return payloadText.includes(selectedMissionUid);
      });
    case "missionChanges":
      return workspace.missionChanges.filter((entry) => String(entry.mission_uid ?? "").trim() === missionUid.value);
    case "logEntries":
      return workspace.logEntries.filter((entry) => String(entry.mission_uid ?? "").trim() === missionUid.value);
    case "topics":
    case "templates":
    case "skills":
    case "teamMemberSkills":
    case "taskSkillRequirements":
      return workspace[props.collectionKey];
    default:
      return workspace[props.collectionKey];
  }
});

const scopedRows = computed<Record<string, unknown>[]>(() => {
  return recordsByKey.value.map((entry) => {
    if (entry && typeof entry === "object") {
      return entry as Record<string, unknown>;
    }
    return { value: entry };
  });
});

const visibleRows = computed(() => scopedRows.value.slice(0, 200));

const columnKeys = computed(() => {
  const keySet = new Set<string>();
  visibleRows.value.forEach((row) => {
    Object.keys(row).forEach((key) => keySet.add(key));
  });
  return [...keySet].sort((left, right) => {
    if (left === "uid") {
      return -1;
    }
    if (right === "uid") {
      return 1;
    }
    return left.localeCompare(right);
  });
});

const formatCell = (value: unknown): string => {
  if (value === null || value === undefined) {
    return "-";
  }
  if (Array.isArray(value)) {
    const next = value
      .map((entry) => formatCell(entry))
      .filter((entry) => entry.length > 0)
      .join(", ");
    return next || "-";
  }
  if (typeof value === "object") {
    try {
      const text = JSON.stringify(value);
      return text.length > 80 ? `${text.slice(0, 80)}...` : text;
    } catch (_error) {
      return "[object]";
    }
  }
  const text = String(value).trim();
  if (!text.length) {
    return "-";
  }
  return text;
};

const prettyColumn = (value: string): string =>
  value
    .replace(/_/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (token) => token.toUpperCase());

const rowKey = (row: Record<string, unknown>, index: number): string => {
  const idCandidate = String(row.uid ?? row.id ?? row.entry_uid ?? row.asset_uid ?? row.assignment_uid ?? "").trim();
  return idCandidate || `${props.collectionKey}-${index}`;
};

const reload = async () => {
  await workspace.loadWorkspace();
};

const openLegacyWorkspace = () => {
  const query: Record<string, string> = {};
  const selectedMissionUid = missionUid.value;
  if (selectedMissionUid) {
    query.mission_uid = selectedMissionUid;
  }
  if (props.legacyScreen) {
    query.screen = props.legacyScreen;
  }
  router
    .push({
      path: props.legacyPath,
      query
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
.mission-domain-record-page {
  min-height: 360px;
}

.domain-actions {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}

.domain-truncate-note {
  margin-top: 0.5rem;
  font-size: 0.7rem;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: rgba(140, 182, 214, 0.8);
}
</style>
