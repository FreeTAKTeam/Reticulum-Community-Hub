<template>
  <div class="mission-assets-workspace">
    <div class="registry-shell">
      <header class="registry-top">
        <div class="registry-title">Mission Asset Registry</div>
        <div class="registry-status">
          <OnlineHelpLauncher />
          <span class="cui-status-pill" :class="connectionClass">{{ connectionLabel }}</span>
          <span class="cui-status-pill" :class="wsClass">{{ wsLabel }}</span>
          <span class="status-url">{{ baseUrl }}</span>
        </div>
      </header>

      <section class="panel control-strip">
        <div class="control-row">
          <div class="control-actions">
            <BaseButton variant="ghost" size="sm" icon-left="chevron-left" @click="goBackToMissions">
              Missions
            </BaseButton>
            <BaseButton variant="secondary" size="sm" icon-left="list" @click="goToMissionLogs">
              Logs
            </BaseButton>
          </div>
          <div class="control-filters">
            <BaseSelect v-model="selectedMissionUid" label="Mission Scope" :options="missionSelectOptions" />
            <label class="filter-field">
              <span>Search</span>
              <input v-model="searchQuery" type="search" placeholder="asset, uid, team member..." />
            </label>
            <BaseSelect v-model="statusFilter" label="Status" :options="statusSelectOptions" />
          </div>
          <div class="control-actions">
            <BaseButton variant="secondary" size="sm" icon-left="refresh" @click="loadWorkspace">
              Refresh
            </BaseButton>
            <BaseButton size="sm" icon-left="plus" @click="openCreateModal">New Asset</BaseButton>
          </div>
        </div>
        <div class="control-meta">
          <span>Visible: {{ formatNumber(visibleAssets.length) }}</span>
          <span>Mission teams: {{ formatNumber(missionTeamCount) }}</span>
          <span>Mission members: {{ formatNumber(missionMemberCount) }}</span>
        </div>
      </section>

      <div class="registry-grid">
        <aside class="panel registry-side">
          <div class="panel-header">
            <div>
              <div class="panel-title">Mission Context</div>
              <div class="panel-subtitle">{{ selectedMissionLabel }}</div>
            </div>
            <div class="panel-chip">{{ missionScopedMemberOptions.length - 1 }} members</div>
          </div>

          <ul class="stack-list">
            <li>
              <strong>Scope</strong>
              <span>{{ selectedMissionLabel }}</span>
            </li>
            <li>
              <strong>Total Assets</strong>
              <span>{{ formatNumber(assetRecords.length) }}</span>
            </li>
            <li>
              <strong>Scoped Assets</strong>
              <span>{{ formatNumber(visibleAssets.length) }}</span>
            </li>
            <li>
              <strong>Last Refresh</strong>
              <span>{{ formatTimestamp(lastRefreshedAt) }}</span>
            </li>
          </ul>

          <div class="member-pool">
            <h4>Assignable Members</h4>
            <div class="member-list">
              <div v-for="member in scopedMemberSummaries" :key="member.uid" class="member-chip">
                <span class="member-name">{{ member.name }}</span>
                <span class="member-team">{{ member.team }}</span>
              </div>
              <p v-if="!scopedMemberSummaries.length" class="empty-copy">
                No members in scope. You can still create unassigned assets.
              </p>
            </div>
          </div>
        </aside>

        <section class="panel registry-main">
          <div class="panel-header">
            <div>
              <div class="panel-title">Asset Inventory</div>
              <div class="panel-subtitle">Create, update, and retire mission-linked equipment</div>
            </div>
          </div>

          <div v-if="loading" class="panel-empty">Loading asset inventory...</div>
          <div v-else-if="!visibleAssets.length" class="panel-empty">No assets found for the current filters.</div>
          <div v-else class="table-wrap cui-scrollbar">
            <table class="mini-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Type</th>
                  <th>Status</th>
                  <th>Team Member</th>
                  <th>Serial</th>
                  <th>Updated</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="asset in visibleAssets" :key="asset.uid">
                  <td>{{ asset.name }}</td>
                  <td>{{ asset.asset_type }}</td>
                  <td>
                    <span class="asset-status" :class="statusClass(asset.status)">{{ asset.status }}</span>
                  </td>
                  <td>{{ asset.team_member_name }}</td>
                  <td>{{ asset.serial_number || "-" }}</td>
                  <td>{{ formatTimestamp(asset.updated_at || asset.created_at) }}</td>
                  <td>
                    <div class="row-actions">
                      <BaseButton size="sm" variant="secondary" icon-left="edit" @click="openEditModal(asset)">
                        Edit
                      </BaseButton>
                      <BaseButton
                        size="sm"
                        variant="danger"
                        icon-left="trash"
                        :disabled="deletingUid === asset.uid"
                        @click="deleteAsset(asset)"
                      >
                        Delete
                      </BaseButton>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>

    <BaseModal :open="editorOpen" :title="editorTitle" @close="closeEditor">
      <form class="editor-form" @submit.prevent="saveAsset">
        <label class="field-control">
          <span>Name</span>
          <input v-model="editor.name" type="text" maxlength="96" required />
        </label>
        <label class="field-control">
          <span>Asset Type</span>
          <input v-model="editor.asset_type" type="text" maxlength="64" placeholder="FIELD_UNIT" required />
        </label>
        <BaseSelect v-model="editor.status" label="Status" :options="assetStatusOptionsForEditor" />
        <BaseSelect v-model="editor.team_member_uid" label="Team Member" :options="missionScopedMemberOptions" />
        <label class="field-control">
          <span>Serial Number</span>
          <input v-model="editor.serial_number" type="text" maxlength="64" />
        </label>
        <label class="field-control">
          <span>Location</span>
          <input v-model="editor.location" type="text" maxlength="128" />
        </label>
        <label class="field-control full">
          <span>Notes</span>
          <textarea v-model="editor.notes" rows="3" maxlength="512"></textarea>
        </label>
        <div class="editor-actions">
          <BaseButton type="button" variant="ghost" size="sm" icon-left="undo" @click="closeEditor">
            Cancel
          </BaseButton>
          <BaseButton type="submit" size="sm" icon-left="save" :disabled="saving">
            {{ editorMode === "edit" ? "Save Asset" : "Create Asset" }}
          </BaseButton>
        </div>
      </form>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { del as deleteRequest, get, post } from "../api/client";
import { endpoints } from "../api/endpoints";
import BaseButton from "../components/BaseButton.vue";
import BaseModal from "../components/BaseModal.vue";
import BaseSelect from "../components/BaseSelect.vue";
import OnlineHelpLauncher from "../components/OnlineHelpLauncher.vue";
import { useConnectionStore } from "../stores/connection";
import { useToastStore } from "../stores/toasts";
import { formatNumber, formatTimestamp } from "../utils/format";

interface MissionRaw {
  uid?: string;
  mission_name?: string | null;
}

interface TeamRaw {
  uid?: string;
  mission_uid?: string | null;
  team_name?: string | null;
}

interface TeamMemberRaw {
  uid?: string;
  team_uid?: string | null;
  display_name?: string | null;
}

interface AssetRaw {
  asset_uid?: string;
  team_member_uid?: string | null;
  name?: string | null;
  asset_type?: string | null;
  serial_number?: string | null;
  status?: string | null;
  location?: string | null;
  notes?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

interface AssignmentRaw {
  mission_uid?: string | null;
  assets?: unknown;
}

interface AssetView {
  uid: string;
  team_member_uid: string;
  name: string;
  asset_type: string;
  serial_number: string;
  status: string;
  location: string;
  notes: string;
  created_at: string;
  updated_at: string;
  team_member_name: string;
}

type EditorMode = "create" | "edit";

const DEFAULT_ASSET_STATUSES = ["AVAILABLE", "IN_USE", "MAINTENANCE", "LOST", "RETIRED"] as const;

const route = useRoute();
const router = useRouter();
const connectionStore = useConnectionStore();
const toastStore = useToastStore();

const missions = ref<MissionRaw[]>([]);
const teamRecords = ref<TeamRaw[]>([]);
const teamMemberRecords = ref<TeamMemberRaw[]>([]);
const assetRecords = ref<AssetRaw[]>([]);
const assignmentRecords = ref<AssignmentRaw[]>([]);

const selectedMissionUid = ref("");
const searchQuery = ref("");
const statusFilter = ref("ALL");
const loading = ref(false);
const saving = ref(false);
const deletingUid = ref("");
const lastRefreshedAt = ref("");

const editorOpen = ref(false);
const editorMode = ref<EditorMode>("create");
const editor = ref({
  asset_uid: "",
  team_member_uid: "",
  name: "",
  asset_type: "FIELD_UNIT",
  serial_number: "",
  status: "AVAILABLE",
  location: "",
  notes: ""
});

const toArray = <T>(value: unknown): T[] => (Array.isArray(value) ? (value as T[]) : []);
const queryText = (value: unknown): string =>
  Array.isArray(value) ? String(value[0] ?? "").trim() : String(value ?? "").trim();
const parseStringList = (value: unknown): string[] =>
  Array.isArray(value) ? value.map((item) => String(item ?? "").trim()).filter((item) => item.length > 0) : [];

const missionByUid = computed(() => {
  const map = new Map<string, string>();
  missions.value.forEach((entry) => {
    const uid = String(entry.uid ?? "").trim();
    if (uid) {
      map.set(uid, String(entry.mission_name ?? uid));
    }
  });
  return map;
});

const memberByUid = computed(() => {
  const map = new Map<string, string>();
  teamMemberRecords.value.forEach((entry) => {
    const uid = String(entry.uid ?? "").trim();
    if (uid) {
      map.set(uid, String(entry.display_name ?? uid));
    }
  });
  return map;
});

const missionTeamUidSet = computed(() => {
  if (!selectedMissionUid.value) {
    return new Set<string>();
  }
  return new Set(
    teamRecords.value
      .filter((entry) => String(entry.mission_uid ?? "").trim() === selectedMissionUid.value)
      .map((entry) => String(entry.uid ?? "").trim())
      .filter((entry) => entry.length > 0)
  );
});

const missionMemberUidSet = computed(() => {
  if (!selectedMissionUid.value) {
    return new Set<string>();
  }
  const teamUids = missionTeamUidSet.value;
  return new Set(
    teamMemberRecords.value
      .filter((entry) => teamUids.has(String(entry.team_uid ?? "").trim()))
      .map((entry) => String(entry.uid ?? "").trim())
      .filter((entry) => entry.length > 0)
  );
});

const missionAssignmentAssetUidSet = computed(() => {
  if (!selectedMissionUid.value) {
    return new Set<string>();
  }
  const set = new Set<string>();
  assignmentRecords.value
    .filter((entry) => String(entry.mission_uid ?? "").trim() === selectedMissionUid.value)
    .forEach((entry) => {
      parseStringList(entry.assets).forEach((assetUid) => set.add(assetUid));
    });
  return set;
});

const missionScopedMemberOptions = computed(() => {
  const scopedSet = missionMemberUidSet.value;
  const source =
    selectedMissionUid.value && scopedSet.size > 0
      ? teamMemberRecords.value.filter((entry) => scopedSet.has(String(entry.uid ?? "").trim()))
      : teamMemberRecords.value;
  const options = source
    .map((entry) => {
      const uid = String(entry.uid ?? "").trim();
      if (!uid) {
        return null;
      }
      const name = String(entry.display_name ?? uid);
      return { value: uid, label: name };
    })
    .filter((entry): entry is { value: string; label: string } => entry !== null)
    .sort((left, right) => left.label.localeCompare(right.label));
  return [{ value: "", label: "Unassigned" }, ...options];
});

const missionSelectOptions = computed(() => {
  const options = missions.value
    .map((entry) => {
      const uid = String(entry.uid ?? "").trim();
      if (!uid) {
        return null;
      }
      return { value: uid, label: String(entry.mission_name ?? uid) };
    })
    .filter((entry): entry is { value: string; label: string } => entry !== null)
    .sort((left, right) => left.label.localeCompare(right.label));
  return [{ value: "", label: "All Missions" }, ...options];
});

const assetStatusOptionsForEditor = computed(() =>
  DEFAULT_ASSET_STATUSES.map((entry) => ({ value: entry, label: entry.replaceAll("_", " ") }))
);

const statusSelectOptions = computed(() => {
  const statuses = new Set<string>(DEFAULT_ASSET_STATUSES);
  assetRecords.value.forEach((entry) => {
    const status = String(entry.status ?? "").trim().toUpperCase();
    if (status) {
      statuses.add(status);
    }
  });
  return [
    { value: "ALL", label: "All Statuses" },
    ...[...statuses].sort().map((entry) => ({ value: entry, label: entry.replaceAll("_", " ") }))
  ];
});

const selectedMissionLabel = computed(() => {
  if (!selectedMissionUid.value) {
    return "All Missions";
  }
  return missionByUid.value.get(selectedMissionUid.value) ?? selectedMissionUid.value;
});

const scopedMemberSummaries = computed(() => {
  const scopedSet = missionMemberUidSet.value;
  const source =
    selectedMissionUid.value && scopedSet.size > 0
      ? teamMemberRecords.value.filter((entry) => scopedSet.has(String(entry.uid ?? "").trim()))
      : teamMemberRecords.value;
  return source
    .map((entry) => {
      const uid = String(entry.uid ?? "").trim();
      if (!uid) {
        return null;
      }
      const teamUid = String(entry.team_uid ?? "").trim();
      const team = teamRecords.value.find((item) => String(item.uid ?? "").trim() === teamUid);
      return {
        uid,
        name: String(entry.display_name ?? uid),
        team: String(team?.team_name ?? "No Team")
      };
    })
    .filter((entry): entry is { uid: string; name: string; team: string } => entry !== null)
    .sort((left, right) => left.name.localeCompare(right.name));
});

const missionTeamCount = computed(() => missionTeamUidSet.value.size);
const missionMemberCount = computed(() => missionMemberUidSet.value.size);

const visibleAssets = computed<AssetView[]>(() => {
  const memberSet = missionMemberUidSet.value;
  const assignmentSet = missionAssignmentAssetUidSet.value;
  const search = searchQuery.value.trim().toLowerCase();
  return assetRecords.value
    .map((entry) => {
      const uid = String(entry.asset_uid ?? "").trim();
      if (!uid) {
        return null;
      }
      const teamMemberUid = String(entry.team_member_uid ?? "").trim();
      const teamMemberName = memberByUid.value.get(teamMemberUid) ?? "Unassigned";
      return {
        uid,
        team_member_uid: teamMemberUid,
        name: String(entry.name ?? uid),
        asset_type: String(entry.asset_type ?? "FIELD_UNIT"),
        serial_number: String(entry.serial_number ?? ""),
        status: String(entry.status ?? "AVAILABLE").toUpperCase(),
        location: String(entry.location ?? ""),
        notes: String(entry.notes ?? ""),
        created_at: String(entry.created_at ?? ""),
        updated_at: String(entry.updated_at ?? ""),
        team_member_name: teamMemberName
      };
    })
    .filter((entry): entry is AssetView => entry !== null)
    .filter((entry) => {
      if (!selectedMissionUid.value) {
        return true;
      }
      if (memberSet.has(entry.team_member_uid)) {
        return true;
      }
      return assignmentSet.has(entry.uid);
    })
    .filter((entry) => statusFilter.value === "ALL" || entry.status === statusFilter.value)
    .filter((entry) => {
      if (!search) {
        return true;
      }
      return [entry.uid, entry.name, entry.asset_type, entry.status, entry.team_member_name, entry.serial_number]
        .join(" ")
        .toLowerCase()
        .includes(search);
    })
    .sort((left, right) => left.name.localeCompare(right.name));
});

const editorTitle = computed(() => (editorMode.value === "edit" ? "Edit Mission Asset" : "Create Mission Asset"));

const connectionClass = computed(() => {
  if (connectionStore.status === "online") {
    return "cui-status-success";
  }
  if (connectionStore.status === "offline") {
    return "cui-status-danger";
  }
  return "cui-status-accent";
});

const wsClass = computed(() => (connectionStore.wsLabel.toLowerCase() === "live" ? "cui-status-success" : "cui-status-accent"));
const baseUrl = computed(() => connectionStore.baseUrlDisplay);
const connectionLabel = computed(() => connectionStore.statusLabel);
const wsLabel = computed(() => connectionStore.wsLabel);

const statusClass = (status: string) => {
  if (status === "AVAILABLE") {
    return "asset-status--available";
  }
  if (status === "IN_USE") {
    return "asset-status--in-use";
  }
  if (status === "MAINTENANCE") {
    return "asset-status--maintenance";
  }
  if (status === "LOST" || status === "RETIRED") {
    return "asset-status--critical";
  }
  return "";
};

const resetEditor = () => {
  editor.value = {
    asset_uid: "",
    team_member_uid: "",
    name: "",
    asset_type: "FIELD_UNIT",
    serial_number: "",
    status: "AVAILABLE",
    location: "",
    notes: ""
  };
};

const openCreateModal = () => {
  editorMode.value = "create";
  resetEditor();
  editorOpen.value = true;
};

const openEditModal = (asset: AssetView) => {
  editorMode.value = "edit";
  editor.value = {
    asset_uid: asset.uid,
    team_member_uid: asset.team_member_uid,
    name: asset.name,
    asset_type: asset.asset_type,
    serial_number: asset.serial_number,
    status: asset.status,
    location: asset.location,
    notes: asset.notes
  };
  editorOpen.value = true;
};

const closeEditor = () => {
  editorOpen.value = false;
};

const saveAsset = async () => {
  const name = editor.value.name.trim();
  const assetType = editor.value.asset_type.trim();
  if (!name || !assetType) {
    toastStore.push("Asset name and type are required", "warning");
    return;
  }
  saving.value = true;
  try {
    const payload: Record<string, unknown> = {
      name,
      asset_type: assetType,
      status: String(editor.value.status || "AVAILABLE"),
      team_member_uid: editor.value.team_member_uid.trim() || null,
      serial_number: editor.value.serial_number.trim() || null,
      location: editor.value.location.trim() || null,
      notes: editor.value.notes.trim() || null
    };
    if (editorMode.value === "edit" && editor.value.asset_uid.trim()) {
      payload.asset_uid = editor.value.asset_uid.trim();
    }
    await post(endpoints.r3aktAssets, payload);
    await loadWorkspace();
    editorOpen.value = false;
    toastStore.push(editorMode.value === "edit" ? "Asset updated" : "Asset created", "success");
  } catch (error) {
    toastStore.push("Unable to save asset", "danger");
  } finally {
    saving.value = false;
  }
};

const deleteAsset = async (asset: AssetView) => {
  const confirmed = window.confirm(`Delete asset "${asset.name}"?`);
  if (!confirmed) {
    return;
  }
  deletingUid.value = asset.uid;
  try {
    await deleteRequest(`${endpoints.r3aktAssets}/${encodeURIComponent(asset.uid)}`);
    await loadWorkspace();
    toastStore.push("Asset deleted", "success");
  } catch (error) {
    toastStore.push("Unable to delete asset", "danger");
  } finally {
    deletingUid.value = "";
  }
};

const goBackToMissions = () => {
  router
    .push({
      path: "/missions",
      query: selectedMissionUid.value ? { mission_uid: selectedMissionUid.value } : undefined
    })
    .catch(() => undefined);
};

const goToMissionLogs = () => {
  router
    .push({
      path: "/missions/logs",
      query: selectedMissionUid.value ? { mission_uid: selectedMissionUid.value } : undefined
    })
    .catch(() => undefined);
};

const loadWorkspace = async () => {
  loading.value = true;
  try {
    const [missionData, teamsData, membersData, assetsData, assignmentsData] = await Promise.all([
      get<MissionRaw[]>(endpoints.r3aktMissions),
      get<TeamRaw[]>(endpoints.r3aktTeams),
      get<TeamMemberRaw[]>(endpoints.r3aktTeamMembers),
      get<AssetRaw[]>(endpoints.r3aktAssets),
      get<AssignmentRaw[]>(endpoints.r3aktAssignments)
    ]);
    missions.value = toArray<MissionRaw>(missionData);
    teamRecords.value = toArray<TeamRaw>(teamsData);
    teamMemberRecords.value = toArray<TeamMemberRaw>(membersData);
    assetRecords.value = toArray<AssetRaw>(assetsData);
    assignmentRecords.value = toArray<AssignmentRaw>(assignmentsData);
    lastRefreshedAt.value = new Date().toISOString();
  } catch (error) {
    toastStore.push("Unable to load mission assets", "danger");
  } finally {
    loading.value = false;
  }
};

watch(
  () => route.query.mission_uid,
  (value) => {
    const next = queryText(value);
    if (next !== selectedMissionUid.value) {
      selectedMissionUid.value = next;
    }
  },
  { immediate: true }
);

watch(selectedMissionUid, (missionUid) => {
  const current = queryText(route.query.mission_uid);
  if (current === missionUid) {
    return;
  }
  const nextQuery = { ...route.query };
  if (missionUid) {
    nextQuery.mission_uid = missionUid;
  } else {
    delete nextQuery.mission_uid;
  }
  router.replace({ path: route.path, query: nextQuery }).catch(() => undefined);
});

watch(
  missions,
  (entries) => {
    if (!selectedMissionUid.value) {
      return;
    }
    const hasSelected = entries.some((entry) => String(entry.uid ?? "").trim() === selectedMissionUid.value);
    if (!hasSelected) {
      selectedMissionUid.value = "";
    }
  },
  { immediate: true }
);

onMounted(() => {
  loadWorkspace().catch(() => undefined);
});
</script>

<style scoped>
.mission-assets-workspace {
  --neon: #37f2ff;
  --panel-dark: rgba(4, 12, 22, 0.96);
  --panel-light: rgba(10, 30, 45, 0.94);
  --amber: #ffb35c;
  color: #dffcff;
  font-family: "Orbitron", "Rajdhani", "Barlow", sans-serif;
}

.registry-shell {
  position: relative;
  padding: 20px 22px 26px;
  border-radius: 18px;
  border: 1px solid rgba(55, 242, 255, 0.25);
  background: radial-gradient(circle at top, rgba(42, 210, 255, 0.12), transparent 55%),
    linear-gradient(145deg, rgba(5, 16, 28, 0.96), rgba(2, 6, 12, 0.98));
  box-shadow: 0 18px 55px rgba(1, 6, 12, 0.65), inset 0 0 0 1px rgba(55, 242, 255, 0.08);
  overflow: hidden;
}

.registry-shell::before {
  content: "";
  position: absolute;
  inset: 0;
  background: radial-gradient(circle at 1px 1px, rgba(55, 242, 255, 0.08) 1px, transparent 0) 0 0 / 18px 18px;
  opacity: 0.6;
  pointer-events: none;
}

.registry-top {
  position: relative;
  display: grid;
  grid-template-columns: 1fr auto;
  align-items: center;
  gap: 16px;
  z-index: 1;
}

.registry-title {
  justify-self: center;
  font-size: 20px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #d4fbff;
  text-shadow: 0 0 12px rgba(55, 242, 255, 0.5);
}

.registry-status {
  display: flex;
  align-items: center;
  gap: 10px;
  justify-self: end;
}

.status-url {
  font-size: 11px;
  letter-spacing: 0.08em;
  color: rgba(215, 243, 255, 0.8);
}

.panel {
  position: relative;
  padding: 16px;
  background: linear-gradient(145deg, var(--panel-light), var(--panel-dark));
  border: 1px solid rgba(55, 242, 255, 0.25);
  box-shadow: inset 0 0 0 1px rgba(55, 242, 255, 0.08), 0 12px 30px rgba(1, 6, 12, 0.6);
  clip-path: polygon(0 0, calc(100% - 24px) 0, 100% 24px, 100% 100%, 24px 100%, 0 calc(100% - 24px));
}

.panel::before {
  content: "";
  position: absolute;
  inset: 0;
  border: 1px solid rgba(55, 242, 255, 0.2);
  clip-path: polygon(
    1px 1px,
    calc(100% - 25px) 1px,
    calc(100% - 1px) 25px,
    calc(100% - 1px) calc(100% - 1px),
    25px calc(100% - 1px),
    1px calc(100% - 25px)
  );
  pointer-events: none;
}

.control-strip {
  margin-top: 14px;
}

.control-row {
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: 12px;
  align-items: end;
}

.control-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.control-filters {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.filter-field {
  display: grid;
  gap: 6px;
}

.filter-field span {
  font-size: 10px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: rgba(205, 248, 255, 0.74);
}

.filter-field input {
  border: 1px solid rgba(55, 242, 255, 0.34);
  border-radius: 8px;
  background: rgba(5, 14, 22, 0.84);
  color: #dffcff;
  padding: 8px 10px;
  font-family: inherit;
  font-size: 12px;
}

.control-meta {
  margin-top: 10px;
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  color: rgba(204, 248, 255, 0.76);
  font-size: 11px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.registry-grid {
  margin-top: 16px;
  display: grid;
  grid-template-columns: minmax(280px, 340px) 1fr;
  gap: 14px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 12px;
}

.panel-title {
  font-size: 14px;
  text-transform: uppercase;
  letter-spacing: 0.16em;
  color: #d1fbff;
}

.panel-subtitle {
  font-size: 11px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: rgba(209, 251, 255, 0.65);
  margin-top: 4px;
}

.panel-chip {
  border: 1px solid rgba(55, 242, 255, 0.45);
  color: rgba(227, 252, 255, 0.85);
  font-size: 10px;
  border-radius: 999px;
  padding: 4px 10px;
  text-transform: uppercase;
  letter-spacing: 0.14em;
}

.stack-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 8px;
}

.stack-list li {
  border: 1px solid rgba(55, 242, 255, 0.2);
  border-radius: 8px;
  background: rgba(7, 18, 28, 0.72);
  padding: 8px;
  display: grid;
  gap: 4px;
}

.stack-list li strong {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.12em;
}

.stack-list li span {
  font-size: 12px;
  color: rgba(204, 248, 255, 0.86);
}

.member-pool {
  margin-top: 12px;
}

.member-pool h4 {
  margin: 0;
  font-size: 11px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.member-list {
  margin-top: 8px;
  display: grid;
  gap: 8px;
  max-height: 280px;
  overflow-y: auto;
}

.member-chip {
  border: 1px solid rgba(55, 242, 255, 0.22);
  border-radius: 8px;
  padding: 8px;
  background: rgba(7, 18, 28, 0.6);
  display: grid;
  gap: 3px;
}

.member-name {
  font-size: 12px;
}

.member-team {
  font-size: 10px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: rgba(200, 244, 255, 0.7);
}

.empty-copy {
  margin: 0;
  font-size: 11px;
  color: rgba(205, 248, 255, 0.75);
}

.table-wrap {
  max-height: 64vh;
  overflow: auto;
}

.mini-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.mini-table th {
  text-align: left;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.16em;
  color: rgba(209, 251, 255, 0.7);
  padding: 8px 6px;
  border-bottom: 1px solid rgba(55, 242, 255, 0.3);
}

.mini-table td {
  padding: 8px 6px;
  border-bottom: 1px solid rgba(55, 242, 255, 0.14);
}

.asset-status {
  display: inline-block;
  border: 1px solid rgba(55, 242, 255, 0.42);
  border-radius: 999px;
  padding: 2px 8px;
  font-size: 10px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.asset-status--available {
  border-color: rgba(58, 244, 179, 0.62);
  color: #42f2b2;
}

.asset-status--in-use {
  border-color: rgba(47, 214, 255, 0.65);
  color: #53efff;
}

.asset-status--maintenance {
  border-color: rgba(255, 178, 92, 0.72);
  color: #ffb35c;
}

.asset-status--critical {
  border-color: rgba(255, 107, 148, 0.72);
  color: #ff97bc;
}

.row-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.panel-empty {
  border: 1px dashed rgba(55, 242, 255, 0.26);
  padding: 18px;
  text-align: center;
  text-transform: uppercase;
  letter-spacing: 0.16em;
  color: rgba(210, 251, 255, 0.68);
}

.editor-form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.field-control {
  display: grid;
  gap: 6px;
}

.field-control.full {
  grid-column: 1 / -1;
}

.field-control span {
  font-size: 10px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: rgba(205, 248, 255, 0.74);
}

.field-control input,
.field-control textarea {
  border: 1px solid rgba(55, 242, 255, 0.34);
  border-radius: 8px;
  background: rgba(5, 14, 22, 0.84);
  color: #dffcff;
  padding: 8px 10px;
  font-family: inherit;
  font-size: 12px;
}

.editor-actions {
  grid-column: 1 / -1;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 8px;
}

@media (max-width: 1200px) {
  .control-row {
    grid-template-columns: 1fr;
  }

  .control-filters {
    grid-template-columns: 1fr;
  }

  .registry-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 800px) {
  .registry-top {
    grid-template-columns: 1fr;
  }

  .registry-status {
    justify-self: center;
    flex-wrap: wrap;
  }

  .editor-form {
    grid-template-columns: 1fr;
  }
}
</style>
