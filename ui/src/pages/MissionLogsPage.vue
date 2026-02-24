<template>
  <div class="mission-logs-workspace">
    <div class="registry-shell">
      <header class="registry-top">
        <div class="registry-title">Mission Logbook</div>
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
            <div class="feed-tabs">
              <button
                type="button"
                class="feed-tab"
                :class="{ active: feedTab === 'entries' }"
                @click="feedTab = 'entries'"
              >
                Log Entries
              </button>
              <button
                type="button"
                class="feed-tab"
                :class="{ active: feedTab === 'events' }"
                @click="feedTab = 'events'"
              >
                Domain Events
              </button>
            </div>
          </div>
        </div>
        <div class="control-meta">
          <span>Scope: {{ selectedMissionLabel }}</span>
          <span>Entries: {{ formatNumber(filteredLogEntries.length) }}</span>
          <span>Events: {{ formatNumber(filteredDomainEvents.length) }}</span>
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
            <BaseSelect v-model="editor.mission_uid" label="Mission" :options="missionSelectOptionsWithoutAll" />
            <label class="field-control full">
              <span>Keywords (comma separated)</span>
              <input v-model="editor.keywords" type="text" placeholder="ops,satcom,sitrep" />
            </label>
            <label class="field-control full">
              <span>Client Time (optional)</span>
              <input v-model="editor.client_time" type="datetime-local" />
            </label>
            <label class="field-control full">
              <span>Content</span>
              <textarea v-model="editor.content" rows="7" maxlength="2000" required></textarea>
            </label>
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
              <div class="panel-title">{{ feedTab === "entries" ? "Mission Log Entries" : "Mission Domain Events" }}</div>
              <div class="panel-subtitle">
                {{ feedTab === "entries" ? "Narrative log stream with mission context" : "Registry/event-sourcing activity feed" }}
              </div>
            </div>
          </div>

          <div v-if="loading" class="panel-empty">Loading mission logs...</div>
          <div v-else-if="feedTab === 'entries' && !filteredLogEntries.length" class="panel-empty">
            No log entries found for current filters.
          </div>
          <div v-else-if="feedTab === 'events' && !filteredDomainEvents.length" class="panel-empty">
            No domain events found for current filters.
          </div>

          <div v-else-if="feedTab === 'entries'" class="entry-list cui-scrollbar">
            <article v-for="entry in filteredLogEntries" :key="entry.entry_uid" class="entry-card">
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
              <div class="entry-meta">
                <span>ID: {{ entry.entry_uid }}</span>
                <span v-if="entry.keywords.length">Keywords: {{ entry.keywords.join(", ") }}</span>
              </div>
            </article>
          </div>

          <div v-else class="event-list cui-scrollbar">
            <article v-for="event in filteredDomainEvents" :key="event.event_uid" class="event-card">
              <div class="event-head">
                <h4>{{ event.event_type }}</h4>
                <span>{{ formatTimestamp(event.created_at) }}</span>
              </div>
              <p class="event-meta">
                Aggregate: {{ event.aggregate_type || "-" }} / {{ event.aggregate_uid || "-" }}
              </p>
              <pre class="event-payload">{{ event.payload_summary }}</pre>
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
import { get, post } from "../api/client";
import { endpoints } from "../api/endpoints";
import BaseButton from "../components/BaseButton.vue";
import BaseSelect from "../components/BaseSelect.vue";
import OnlineHelpLauncher from "../components/OnlineHelpLauncher.vue";
import { useConnectionStore } from "../stores/connection";
import { useToastStore } from "../stores/toasts";
import { formatNumber, formatTimestamp } from "../utils/format";

interface MissionRaw {
  uid?: string;
  mission_name?: string | null;
}

interface LogEntryRaw {
  entry_uid?: string;
  mission_uid?: string | null;
  content?: string | null;
  server_time?: string | null;
  client_time?: string | null;
  keywords?: unknown;
}

interface DomainEventRaw {
  event_uid?: string;
  aggregate_type?: string | null;
  aggregate_uid?: string | null;
  event_type?: string | null;
  payload?: unknown;
  created_at?: string | null;
}

interface LogEntryView {
  entry_uid: string;
  mission_uid: string;
  content: string;
  server_time: string;
  client_time: string;
  keywords: string[];
}

interface DomainEventView {
  event_uid: string;
  aggregate_type: string;
  aggregate_uid: string;
  event_type: string;
  created_at: string;
  payload_summary: string;
}

type FeedTab = "entries" | "events";

const route = useRoute();
const router = useRouter();
const connectionStore = useConnectionStore();
const toastStore = useToastStore();

const missions = ref<MissionRaw[]>([]);
const logEntries = ref<LogEntryRaw[]>([]);
const domainEvents = ref<DomainEventRaw[]>([]);

const selectedMissionUid = ref("");
const searchQuery = ref("");
const feedTab = ref<FeedTab>("entries");
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
  content: "",
  keywords: "",
  client_time: toNowDateTimeLocal()
});

const toArray = <T>(value: unknown): T[] => (Array.isArray(value) ? (value as T[]) : []);
const queryText = (value: unknown): string =>
  Array.isArray(value) ? String(value[0] ?? "").trim() : String(value ?? "").trim();
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
        content: String(entry.content ?? ""),
        server_time: String(entry.server_time ?? ""),
        client_time: String(entry.client_time ?? ""),
        keywords: toStringList(entry.keywords)
      };
    })
    .filter((entry): entry is LogEntryView => entry !== null)
    .filter((entry) => !selectedMissionUid.value || entry.mission_uid === selectedMissionUid.value)
    .filter((entry) => {
      if (!search) {
        return true;
      }
      return [entry.entry_uid, entry.content, entry.mission_uid, entry.keywords.join(" ")].join(" ").toLowerCase().includes(search);
    })
    .sort((left, right) => {
      const leftTime = Date.parse(left.server_time || left.client_time || "");
      const rightTime = Date.parse(right.server_time || right.client_time || "");
      return (Number.isNaN(rightTime) ? 0 : rightTime) - (Number.isNaN(leftTime) ? 0 : leftTime);
    });
});

const filteredDomainEvents = computed<DomainEventView[]>(() => {
  const search = searchQuery.value.trim().toLowerCase();
  return domainEvents.value
    .map((entry) => {
      const uid = String(entry.event_uid ?? "").trim();
      if (!uid) {
        return null;
      }
      const payloadSummary = summarizePayload(entry.payload);
      return {
        event_uid: uid,
        aggregate_type: String(entry.aggregate_type ?? ""),
        aggregate_uid: String(entry.aggregate_uid ?? ""),
        event_type: String(entry.event_type ?? ""),
        created_at: String(entry.created_at ?? ""),
        payload_summary: payloadSummary
      };
    })
    .filter((entry): entry is DomainEventView => entry !== null)
    .filter((entry) => {
      if (!selectedMissionUid.value) {
        return true;
      }
      return entry.aggregate_uid === selectedMissionUid.value || entry.payload_summary.includes(selectedMissionUid.value);
    })
    .filter((entry) => {
      if (!search) {
        return true;
      }
      return [entry.event_type, entry.aggregate_uid, entry.payload_summary].join(" ").toLowerCase().includes(search);
    })
    .sort((left, right) => {
      const leftTime = Date.parse(left.created_at);
      const rightTime = Date.parse(right.created_at);
      return (Number.isNaN(rightTime) ? 0 : rightTime) - (Number.isNaN(leftTime) ? 0 : leftTime);
    });
});

const editorTitle = computed(() => (editor.value.entry_uid ? "Edit Log Entry" : "Write Log Entry"));

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

const summarizePayload = (payload: unknown): string => {
  if (payload === null || payload === undefined) {
    return "{}";
  }
  if (typeof payload === "string") {
    return payload.length > 260 ? `${payload.slice(0, 260)}...` : payload;
  }
  try {
    const text = JSON.stringify(payload, null, 2);
    return text.length > 900 ? `${text.slice(0, 900)}...` : text;
  } catch (error) {
    return String(payload);
  }
};

const missionLabel = (missionUid: string) => missionByUid.value.get(missionUid) ?? missionUid;

const resetEditor = () => {
  editor.value = {
    entry_uid: "",
    mission_uid: selectedMissionUid.value || missionSelectOptionsWithoutAll.value[0]?.value || "",
    content: "",
    keywords: "",
    client_time: toNowDateTimeLocal()
  };
};

const editEntry = (entry: LogEntryView) => {
  editor.value = {
    entry_uid: entry.entry_uid,
    mission_uid: entry.mission_uid,
    content: entry.content,
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
  const content = editor.value.content.trim();
  if (!missionUid) {
    toastStore.push("Select a mission before writing the log entry", "warning");
    return;
  }
  if (!content) {
    toastStore.push("Log content cannot be empty", "warning");
    return;
  }
  submitting.value = true;
  try {
    const payload: Record<string, unknown> = {
      mission_uid: missionUid,
      content,
      keywords: editor.value.keywords
        .split(",")
        .map((entry) => entry.trim())
        .filter((entry) => entry.length > 0)
    };
    if (editor.value.entry_uid.trim()) {
      payload.entry_uid = editor.value.entry_uid.trim();
    }
    if (editor.value.client_time.trim()) {
      payload.client_time = new Date(editor.value.client_time).toISOString();
    }
    await post(endpoints.r3aktLogEntries, payload);
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
    const [missionData, logEntryData, eventData] = await Promise.all([
      get<MissionRaw[]>(endpoints.r3aktMissions),
      get<LogEntryRaw[]>(buildLogEntriesPath()),
      get<DomainEventRaw[]>(endpoints.r3aktEvents)
    ]);
    missions.value = toArray<MissionRaw>(missionData);
    logEntries.value = toArray<LogEntryRaw>(logEntryData);
    domainEvents.value = toArray<DomainEventRaw>(eventData);
    lastRefreshedAt.value = new Date().toISOString();
    if (!editor.value.mission_uid) {
      editor.value.mission_uid = selectedMissionUid.value || missionSelectOptionsWithoutAll.value[0]?.value || "";
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
    editor.value.mission_uid = missionUid || missionSelectOptionsWithoutAll.value[0]?.value || "";
  }
  loadWorkspace().catch(() => undefined);
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
  resetEditor();
  loadWorkspace().catch(() => undefined);
});
</script>

<style scoped>
.mission-logs-workspace {
  --neon: #37f2ff;
  --panel-dark: rgba(4, 12, 22, 0.96);
  --panel-light: rgba(10, 30, 45, 0.94);
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
  grid-template-columns: 300px 1fr;
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

.feed-tabs {
  display: inline-flex;
  gap: 4px;
  padding: 4px;
  border-radius: 999px;
  border: 1px solid rgba(55, 242, 255, 0.28);
  background: rgba(7, 18, 26, 0.82);
}

.feed-tab {
  border: 1px solid transparent;
  background: transparent;
  color: rgba(209, 251, 255, 0.6);
  border-radius: 999px;
  padding: 6px 12px;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.16em;
  cursor: pointer;
}

.feed-tab.active {
  border-color: rgba(55, 242, 255, 0.65);
  color: #e0feff;
  background: rgba(55, 242, 255, 0.12);
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
  grid-template-columns: minmax(320px, 380px) 1fr;
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

.editor-form {
  display: grid;
  gap: 10px;
}

.field-control {
  display: grid;
  gap: 6px;
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
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.editor-note {
  margin: 10px 0 0;
  font-size: 11px;
  color: rgba(205, 248, 255, 0.78);
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.panel-empty {
  border: 1px dashed rgba(55, 242, 255, 0.26);
  padding: 18px;
  text-align: center;
  text-transform: uppercase;
  letter-spacing: 0.16em;
  color: rgba(210, 251, 255, 0.68);
}

.entry-list,
.event-list {
  display: grid;
  gap: 10px;
  max-height: 64vh;
  overflow: auto;
  padding-right: 4px;
}

.entry-card,
.event-card {
  border: 1px solid rgba(55, 242, 255, 0.24);
  border-radius: 10px;
  background: rgba(7, 18, 28, 0.68);
  padding: 10px;
  display: grid;
  gap: 8px;
}

.entry-head,
.event-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: flex-start;
}

.entry-head h4,
.event-head h4 {
  margin: 0;
  font-size: 12px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.entry-head p,
.event-head span {
  margin: 4px 0 0;
  font-size: 11px;
  color: rgba(201, 248, 255, 0.72);
}

.entry-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.entry-content {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 13px;
  line-height: 1.45;
}

.entry-meta {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  font-size: 10px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: rgba(196, 246, 255, 0.72);
}

.event-meta {
  margin: 0;
  font-size: 10px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: rgba(196, 246, 255, 0.72);
}

.event-payload {
  margin: 0;
  font-size: 11px;
  border: 1px solid rgba(55, 242, 255, 0.2);
  border-radius: 8px;
  background: rgba(4, 14, 22, 0.82);
  padding: 10px;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 240px;
  overflow: auto;
}

@media (max-width: 1250px) {
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
}
</style>
