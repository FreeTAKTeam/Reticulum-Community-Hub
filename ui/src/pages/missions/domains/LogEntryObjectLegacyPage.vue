<template>
  <div class="mission-logs-workspace">
    <div class="registry-shell">
      <CosmicTopStatus title="Mission Logbook" />

      <section class="panel control-strip">
        <div class="control-row">
          <div class="control-actions">
            <BaseButton variant="ghost" size="sm" icon-left="chevron-left" @click="goBackToMissions">
              Missions
            </BaseButton>
            <BaseButton variant="secondary" size="sm" icon-left="layers" @click="goToMissionAssets">
              Assets
            </BaseButton>
          </div>
          <div class="control-filters">
            <BaseSelect v-model="selectedMissionUid" label="Mission Scope" :options="missionSelectOptions" />
            <label class="filter-field">
              <span>Search</span>
              <input v-model="searchQuery" type="search" placeholder="content, keyword, event type..." />
            </label>
          </div>
          <div class="control-actions">
            <BaseButton variant="secondary" size="sm" icon-left="refresh" @click="loadWorkspace">
              Refresh
            </BaseButton>
          </div>
        </div>
        <div class="control-meta">
          <span>Scope: {{ selectedMissionLabel }}</span>
          <span>Entries: {{ formatNumber(filteredLogEntries.length) }}</span>
        </div>
      </section>

      <div class="registry-grid">
        <aside class="panel registry-side">
          <div class="panel-header">
            <div>
              <div class="panel-title">{{ editorTitle }}</div>
              <div class="panel-subtitle">Create or update mission log entries</div>
            </div>
            <div class="panel-chip">{{ editor.entry_uid ? "Edit" : "New" }}</div>
          </div>

          <form class="editor-form" @submit.prevent="saveLogEntry">
            <BaseSelect v-model="editor.mission_uid" label="Mission (optional)" :options="editorMissionOptions" />
            <label class="field-control full">
              <span>Author Callsign (optional)</span>
              <input v-model="editor.callsign" type="text" maxlength="64" placeholder="EAGLE-1" />
            </label>
            <label class="field-control full">
              <span>Keywords (comma separated)</span>
              <input v-model="editor.keywords" type="text" placeholder="ops,satcom,sitrep" />
            </label>
            <label class="field-control full">
              <span>Client Time (optional)</span>
              <input v-model="editor.client_time" type="datetime-local" />
            </label>
            <div class="mecp-compose">
              <BaseSelect v-model="mecpDraft.severity" label="Severity" :options="mecpSeverityOptions" />
              <BaseSelect v-model="mecpDraft.category" label="Category" :options="mecpCategoryOptions" />
              <BaseSelect v-model="mecpDraft.eventCode" label="Event" :options="mecpEventOptions" />
              <label class="field-control full">
                <span>{{ mecpEnabled ? "Details" : "Text" }}</span>
                <textarea
                  v-model="editor.content"
                  rows="7"
                  maxlength="2000"
                  :placeholder="mecpEnabled ? 'Poco' : 'Canonical log text'"
                  required
                ></textarea>
              </label>
              <div v-if="mecpEnabled" class="mecp-preview">
                <span>MECP Preview</span>
                <strong>{{ mecpPreview }}</strong>
              </div>
              <div v-else class="mecp-preview canonical-preview">
                <span>Canonical Text</span>
                <strong>Saved as plain mission log content</strong>
              </div>
            </div>
            <div class="editor-actions">
              <BaseButton type="button" variant="ghost" size="sm" icon-left="undo" @click="resetEditor">
                Reset
              </BaseButton>
              <BaseButton type="submit" size="sm" icon-left="save" :disabled="submitting">
                {{ editor.entry_uid ? "Update Entry" : "Write Entry" }}
              </BaseButton>
            </div>
          </form>

          <p class="editor-note">
            Log deletion is intentionally unavailable in the current northbound API contract.
          </p>
          <p class="editor-note">Last refresh: {{ formatTimestamp(lastRefreshedAt) }}</p>
        </aside>

        <section class="panel registry-main">
          <div class="panel-header">
            <div>
              <div class="panel-title">Mission Log Entries</div>
              <div class="panel-subtitle">Narrative log stream with mission context</div>
            </div>
            <BaseSelect v-model="logQuickFilter" label="Filter" :options="logQuickFilters" />
          </div>

          <div v-if="loading" class="panel-empty">Loading mission logs...</div>
          <div v-else-if="!filteredLogEntries.length" class="panel-empty">
            No log entries found for current filters.
          </div>

          <div v-else class="entry-list cui-scrollbar">
            <article v-for="entry in filteredLogEntries" :key="entry.entry_uid" class="entry-card" :class="{ 'entry-card-mecp': entry.mecp }">
              <div class="entry-head">
                <div>
                  <h4>{{ missionLabel(entry.mission_uid) }}</h4>
                  <p>{{ formatTimestamp(entry.server_time || entry.client_time) }}</p>
                </div>
                <div class="entry-actions">
                  <BaseButton size="sm" variant="secondary" icon-left="edit" @click="editEntry(entry)">
                    Edit
                  </BaseButton>
                  <BaseButton size="sm" variant="secondary" icon-left="file" @click="copyEntry(entry)">
                    Copy
                  </BaseButton>
                </div>
              </div>
              <p class="entry-content">{{ entry.content }}</p>
              <div v-if="entry.mecp" class="mecp-summary" :class="`mecp-summary-${entry.mecp.severityStatus}`">
                <div class="mecp-summary-head">
                  <span class="mecp-badge">MECP</span>
                  <span class="mecp-field-id">FIELD_EVENT 0x0D</span>
                </div>
                <div class="mecp-decoder-grid">
                  <div class="mecp-decoder-cell">
                    <span>Severity</span>
                    <strong class="mecp-severity">{{ entry.mecp.severityLabel }}</strong>
                  </div>
                  <div class="mecp-decoder-cell">
                    <span>Category</span>
                    <strong>{{ entry.mecp.categoryLabel }}</strong>
                  </div>
                  <div class="mecp-decoder-cell">
                    <span>Event</span>
                    <strong>{{ entry.mecp.codeLabels[0] || "MECP Event" }}</strong>
                  </div>
                  <div class="mecp-decoder-cell">
                    <span>Details</span>
                    <strong>{{ entry.mecp.details || "-" }}</strong>
                  </div>
                </div>
                <div v-if="entry.mecp.extraLabels.length" class="mecp-extra-list">
                  <span v-for="extra in entry.mecp.extraLabels" :key="extra">{{ extra }}</span>
                </div>
                <p class="mecp-details">{{ entry.mecp.raw || entry.content }}</p>
                <p v-if="entry.mecp.warnings.length" class="mecp-warning">{{ entry.mecp.warnings.join(" ") }}</p>
              </div>
              <div class="entry-meta">
                <span>ID: {{ entry.entry_uid }}</span>
                <span v-if="entry.callsign">Callsign: {{ entry.callsign }}</span>
                <span v-if="entry.keywords.length">Keywords: {{ entry.keywords.join(", ") }}</span>
              </div>
            </article>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { get, post } from "../../../api/client";
import { endpoints } from "../../../api/endpoints";
import BaseButton from "../../../components/BaseButton.vue";
import CosmicTopStatus from "../../../components/cosmic/CosmicTopStatus.vue";
import BaseSelect from "../../../components/BaseSelect.vue";
import { useToastStore } from "../../../stores/toasts";
import { formatNumber, formatTimestamp } from "../../../utils/format";
import { encodeMecpLogContent } from "../../../utils/mecp-compose";
import { normalizeMecpDisplay, type MecpDisplay } from "../../../utils/mecp-display";

interface MissionRaw {
  uid?: string;
  mission_name?: string | null;
}

interface LogEntryRaw {
  entry_uid?: string;
  mission_uid?: string | null;
  callsign?: string | null;
  content?: string | null;
  server_time?: string | null;
  client_time?: string | null;
  keywords?: unknown;
  mecp?: unknown;
}

interface LogEntryView {
  entry_uid: string;
  mission_uid: string;
  callsign: string;
  content: string;
  server_time: string;
  client_time: string;
  keywords: string[];
  mecp: MecpDisplay | null;
}

type LogQuickFilter = "all" | "mecp" | "urgent" | "safety";

interface SelectOption {
  value: string;
  label: string;
}

const mecpSeverityOptions: SelectOption[] = [
  { value: "0", label: "Mayday - Critical" },
  { value: "1", label: "Urgent - Challenge" },
  { value: "2", label: "Safety - OK" },
  { value: "3", label: "Routine - Normal" }
];

const mecpCategoryOptions: SelectOption[] = [
  { value: "M", label: "Medical" },
  { value: "T", label: "Terrain / Infrastructure" },
  { value: "W", label: "Weather / Environment" },
  { value: "S", label: "Supplies" },
  { value: "P", label: "Position / Movement" },
  { value: "C", label: "Coordination" },
  { value: "R", label: "Response" },
  { value: "D", label: "Drill / Test" },
  { value: "L", label: "Life / Leisure" },
  { value: "X", label: "Threat / Security" },
  { value: "H", label: "Have / Offer Resources" },
  { value: "B", label: "Beacon" }
];

const mecpEventsByCategory: Record<string, SelectOption[]> = {
  M: [
    { value: "M01", label: "M01 Injury" },
    { value: "M06", label: "M06 Severe bleeding" },
    { value: "M14", label: "M14 Persons located alive" }
  ],
  T: [
    { value: "T01", label: "T01 Road blocked" },
    { value: "T02", label: "T02 Bridge out" },
    { value: "T06", label: "T06 Power out" },
    { value: "T16", label: "T16 Vehicle accident" }
  ],
  W: [
    { value: "W01", label: "W01 Storm approaching" },
    { value: "W02", label: "W02 Visibility zero" },
    { value: "W05", label: "W05 Air quality danger" }
  ],
  S: [
    { value: "S01", label: "S01 Need water" },
    { value: "S02", label: "S02 Need food" },
    { value: "S03", label: "S03 Need medication" },
    { value: "S04", label: "S04 Need battery / power" }
  ],
  P: [
    { value: "P01", label: "P01 Stranded / stuck" },
    { value: "P02", label: "P02 Evacuating toward" },
    { value: "P03", label: "P03 Sheltering in place" },
    { value: "P05", label: "P05 At GPS coordinates" }
  ],
  C: [
    { value: "C01", label: "C01 Send rescue" },
    { value: "C04", label: "C04 Confirm received" },
    { value: "C08", label: "C08 Rendezvous at" }
  ],
  R: [
    { value: "R01", label: "R01 Acknowledged" },
    { value: "R02", label: "R02 Help coming" },
    { value: "R03", label: "R03 ETA [minutes]" }
  ],
  D: [
    { value: "D01", label: "D01 This is a drill" },
    { value: "D02", label: "D02 This is a test" }
  ],
  L: [
    { value: "L07", label: "L07 Good signal here" },
    { value: "L20", label: "L20 Node test / ping" }
  ],
  X: [
    { value: "X01", label: "X01 Dangerous person / threat nearby" },
    { value: "X02", label: "X02 Area unsafe - avoid" }
  ],
  H: [
    { value: "H01", label: "H01 Have water available" },
    { value: "H04", label: "H04 Have power / charging" },
    { value: "H08", label: "H08 Have transport / vehicle" }
  ],
  B: [
    { value: "B01", label: "B01 Automated distress beacon active" },
    { value: "B03", label: "B03 Cancel beacon - I am OK" }
  ]
};

const logQuickFilters: Array<{ value: LogQuickFilter; label: string }> = [
  { value: "all", label: "All" },
  { value: "mecp", label: "MECP" },
  { value: "urgent", label: "Urgent" },
  { value: "safety", label: "Safety" }
];

const route = useRoute();
const router = useRouter();
const toastStore = useToastStore();
const MISSION_WRITE_TIMEOUT_MS = 30000;

const missions = ref<MissionRaw[]>([]);
const logEntries = ref<LogEntryRaw[]>([]);

const queryText = (value: unknown): string =>
  Array.isArray(value) ? String(value[0] ?? "").trim() : String(value ?? "").trim();
const selectedMissionUid = ref(queryText(route.query.mission_uid));
const searchQuery = ref("");
const logQuickFilter = ref<LogQuickFilter>("all");
const loading = ref(false);
const submitting = ref(false);
const lastRefreshedAt = ref("");

function toNowDateTimeLocal(): string {
  const date = new Date();
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `${year}-${month}-${day}T${hours}:${minutes}`;
}

const editor = ref({
  entry_uid: "",
  mission_uid: "",
  callsign: "",
  content: "",
  keywords: "",
  client_time: toNowDateTimeLocal()
});

const mecpDraft = ref({
  severity: "1",
  category: "S",
  eventCode: ""
});

const toArray = <T>(value: unknown): T[] => {
  if (Array.isArray(value)) {
    return value as T[];
  }
  if (value && typeof value === "object" && Array.isArray((value as { value?: unknown }).value)) {
    return (value as { value: T[] }).value;
  }
  return [];
};
const toStringList = (value: unknown): string[] =>
  Array.isArray(value)
    ? value.map((item) => String(item ?? "").trim()).filter((item) => item.length > 0)
    : [];

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

const missionSelectOptionsWithoutAll = computed(() =>
  missionSelectOptions.value.filter((entry) => entry.value.length > 0)
);
const editorMissionOptions = computed(() => [
  { value: "", label: "Mission Default" },
  ...missionSelectOptionsWithoutAll.value
]);

const mecpEventOptions = computed(() => [
  { value: "", label: "No MECP event" },
  ...(mecpEventsByCategory[mecpDraft.value.category] ?? [])
]);

const mecpEnabled = computed(() => mecpDraft.value.eventCode.trim().length > 0);

const mecpPreview = computed(() => {
  if (!mecpEnabled.value) {
    return editor.value.content.trim();
  }
  return encodeMecpLogContent({
    severity: mecpDraft.value.severity,
    eventCode: mecpDraft.value.eventCode,
    details: editor.value.content
  });
});

const selectedMissionLabel = computed(() => {
  if (!selectedMissionUid.value) {
    return "All Missions";
  }
  return missionByUid.value.get(selectedMissionUid.value) ?? selectedMissionUid.value;
});

const filteredLogEntries = computed<LogEntryView[]>(() => {
  const search = searchQuery.value.trim().toLowerCase();
  return logEntries.value
    .map((entry) => {
      const uid = String(entry.entry_uid ?? "").trim();
      if (!uid) {
        return null;
      }
      return {
        entry_uid: uid,
        mission_uid: String(entry.mission_uid ?? "").trim(),
        callsign: String(entry.callsign ?? "").trim(),
        content: String(entry.content ?? ""),
        server_time: String(entry.server_time ?? ""),
        client_time: String(entry.client_time ?? ""),
        keywords: toStringList(entry.keywords),
        mecp: normalizeMecpDisplay(entry.mecp, entry.content)
      };
    })
    .filter((entry): entry is LogEntryView => entry !== null)
    .filter((entry) => !selectedMissionUid.value || entry.mission_uid === selectedMissionUid.value)
    .filter((entry) => {
      if (logQuickFilter.value === "all") {
        return true;
      }
      if (logQuickFilter.value === "mecp") {
        return Boolean(entry.mecp);
      }
      if (logQuickFilter.value === "urgent") {
        return entry.mecp?.severityLabel === "Urgent";
      }
      if (logQuickFilter.value === "safety") {
        return entry.mecp?.severityLabel === "Safety";
      }
      return true;
    })
    .filter((entry) => {
      if (!search) {
        return true;
      }
      return [
        entry.entry_uid,
        entry.callsign,
        entry.content,
        entry.mission_uid,
        entry.keywords.join(" "),
        entry.mecp?.categoryLabel ?? "",
        entry.mecp?.severityLabel ?? "",
        entry.mecp?.codeLabels.join(" ") ?? ""
      ].join(" ").toLowerCase().includes(search);
    })
    .sort((left, right) => {
      const leftTime = Date.parse(left.server_time || left.client_time || "");
      const rightTime = Date.parse(right.server_time || right.client_time || "");
      return (Number.isNaN(rightTime) ? 0 : rightTime) - (Number.isNaN(leftTime) ? 0 : leftTime);
    });
});

const editorTitle = computed(() => (editor.value.entry_uid ? "Edit Log Entry" : "Write Log Entry"));

const missionLabel = (missionUid: string) => missionByUid.value.get(missionUid) ?? missionUid;

const restoreMecpDraftFromContent = (content: string) => {
  const match = /^MECP\/([0-3])\/(.+)$/i.exec(content.trim());
  if (!match) {
    mecpDraft.value = {
      severity: "1",
      category: "S",
      eventCode: ""
    };
    return content;
  }

  const tokens = match[2].trim().split(/\s+/).filter((token) => token.length > 0);
  const eventCode = String(tokens[0] ?? "").toUpperCase();
  const detailsStart = tokens.findIndex((token) => !/^[A-Z][0-9]{2}$/i.test(token));
  const details = detailsStart >= 0 ? tokens.slice(detailsStart).join(" ") : "";
  mecpDraft.value = {
    severity: match[1],
    category: eventCode.slice(0, 1) || "S",
    eventCode
  };
  return details;
};

const resetEditor = () => {
  editor.value = {
    entry_uid: "",
    mission_uid: selectedMissionUid.value || "",
    callsign: "",
    content: "",
    keywords: "",
    client_time: toNowDateTimeLocal()
  };
  mecpDraft.value = {
    severity: "1",
    category: "S",
    eventCode: ""
  };
};

const editEntry = (entry: LogEntryView) => {
  const content = restoreMecpDraftFromContent(entry.content);
  editor.value = {
    entry_uid: entry.entry_uid,
    mission_uid: entry.mission_uid,
    callsign: entry.callsign,
    content,
    keywords: entry.keywords.join(", "),
    client_time: toDateTimeLocal(entry.client_time || entry.server_time)
  };
};

const toDateTimeLocal = (value?: string): string => {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `${year}-${month}-${day}T${hours}:${minutes}`;
};

const saveLogEntry = async () => {
  const missionUid = editor.value.mission_uid.trim();
  const callsign = editor.value.callsign.trim();
  const content = mecpEnabled.value ? mecpPreview.value : editor.value.content.trim();
  if (!content) {
    toastStore.push("Log content cannot be empty", "warning");
    return;
  }
  submitting.value = true;
  try {
    const payload: Record<string, unknown> = {
      content,
      keywords: editor.value.keywords
        .split(",")
        .map((entry) => entry.trim())
        .filter((entry) => entry.length > 0)
    };
    if (missionUid) {
      payload.mission_uid = missionUid;
    }
    if (callsign) {
      payload.callsign = callsign;
    }
    if (editor.value.entry_uid.trim()) {
      payload.entry_uid = editor.value.entry_uid.trim();
    }
    if (editor.value.client_time.trim()) {
      payload.client_time = new Date(editor.value.client_time).toISOString();
    }
    await post(endpoints.r3aktLogEntries, payload, { timeoutMs: MISSION_WRITE_TIMEOUT_MS });
    await loadWorkspace();
    toastStore.push(editor.value.entry_uid ? "Log entry updated" : "Log entry created", "success");
    resetEditor();
  } catch (error) {
    toastStore.push("Unable to save log entry", "danger");
  } finally {
    submitting.value = false;
  }
};

const copyEntry = async (entry: LogEntryView) => {
  try {
    await navigator.clipboard.writeText(
      JSON.stringify(
        {
          entry_uid: entry.entry_uid,
          mission_uid: entry.mission_uid,
          callsign: entry.callsign || null,
          server_time: entry.server_time,
          client_time: entry.client_time,
          keywords: entry.keywords,
          content: entry.content
        },
        null,
        2
      )
    );
    toastStore.push("Log entry copied", "success");
  } catch (error) {
    toastStore.push("Unable to copy log entry", "warning");
  }
};

const buildLogEntriesPath = () => {
  if (!selectedMissionUid.value) {
    return endpoints.r3aktLogEntries;
  }
  const mission = encodeURIComponent(selectedMissionUid.value);
  return `${endpoints.r3aktLogEntries}?mission_uid=${mission}`;
};

const loadWorkspace = async () => {
  loading.value = true;
  try {
    const [missionData, logEntryData] = await Promise.all([
      get<MissionRaw[]>(endpoints.r3aktMissions),
      get<LogEntryRaw[]>(buildLogEntriesPath())
    ]);
    missions.value = toArray<MissionRaw>(missionData);
    logEntries.value = toArray<LogEntryRaw>(logEntryData);
    const routeMissionUid = queryText(route.query.mission_uid);
    if (
      routeMissionUid &&
      missions.value.some((entry) => String(entry.uid ?? "").trim() === routeMissionUid)
    ) {
      selectedMissionUid.value = routeMissionUid;
    }
    lastRefreshedAt.value = new Date().toISOString();
    if (!editor.value.mission_uid) {
      editor.value.mission_uid = selectedMissionUid.value || "";
    }
  } catch (error) {
    toastStore.push("Unable to load mission logs", "danger");
  } finally {
    loading.value = false;
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

const goToMissionAssets = () => {
  router
    .push({
      path: "/missions/assets",
      query: selectedMissionUid.value ? { mission_uid: selectedMissionUid.value } : undefined
    })
    .catch(() => undefined);
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
  if (current !== missionUid) {
    const nextQuery = { ...route.query };
    if (missionUid) {
      nextQuery.mission_uid = missionUid;
    } else {
      delete nextQuery.mission_uid;
    }
    router.replace({ path: route.path, query: nextQuery }).catch(() => undefined);
  }
  if (!editor.value.entry_uid) {
    editor.value.mission_uid = missionUid || "";
  }
  loadWorkspace().catch(() => undefined);
});

watch(
  () => mecpDraft.value.category,
  (category) => {
    if (!mecpDraft.value.eventCode) {
      return;
    }
    const options = mecpEventsByCategory[category] ?? [];
    if (!options.some((option) => option.value === mecpDraft.value.eventCode)) {
      mecpDraft.value.eventCode = options[0]?.value ?? "";
    }
  }
);

watch(
  missions,
  (entries) => {
    if (!selectedMissionUid.value || !entries.length) {
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
  resetEditor();
  loadWorkspace().catch(() => undefined);
});
</script>

<style scoped src="../../styles/MissionLogsPage.css"></style>
