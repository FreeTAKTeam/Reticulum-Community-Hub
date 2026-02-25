<template>
  <div class="mission-assets-workspace">
    <div class="registry-shell">
      <CosmicTopStatus title="Mission Asset Registry" />

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
import CosmicTopStatus from "../components/cosmic/CosmicTopStatus.vue";
import BaseModal from "../components/BaseModal.vue";
import BaseSelect from "../components/BaseSelect.vue";
import { useToastStore } from "../stores/toasts";
import { formatNumber, formatTimestamp } from "../utils/format";
import { resolveTeamMemberPrimaryLabel } from "../utils/team-members";

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
  callsign?: string | null;
  rns_identity?: string | null;
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

const teamMemberPrimaryLabel = (entry: TeamMemberRaw): string =>
  resolveTeamMemberPrimaryLabel(entry, { uid: String(entry.uid ?? "").trim() });

const memberByUid = computed(() => {
  const map = new Map<string, string>();
  teamMemberRecords.value.forEach((entry) => {
    const uid = String(entry.uid ?? "").trim();
    if (uid) {
      map.set(uid, teamMemberPrimaryLabel(entry));
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
      const name = teamMemberPrimaryLabel(entry);
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
        name: teamMemberPrimaryLabel(entry),
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

<style scoped src="./styles/MissionAssetsPage.css"></style>




