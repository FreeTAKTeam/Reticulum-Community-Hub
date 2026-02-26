<template>
  <div class="about-cosmos">
    <div class="about-shell">
      <header class="about-top">
        <div>
          <div class="about-title">System Dossier</div>
          <div class="about-subtitle">Reticulum Telemetry Hub identity, runtime profile, and reference channels</div>
        </div>
        <div class="about-badges">
          <div class="about-badge">
            <span>Version</span>
            <strong>{{ formatValue(appInfo?.version) }}</strong>
          </div>
          <div class="about-badge">
            <span>Transport</span>
            <strong :class="appInfo?.is_transport_enabled ? 'state-ok' : 'state-warn'">
              {{ formatFlag(appInfo?.is_transport_enabled) }}
            </strong>
          </div>
          <div class="about-badge">
            <span>Shared</span>
            <strong :class="appInfo?.is_connected_to_shared_instance ? 'state-ok' : 'state-idle'">
              {{ formatFlag(appInfo?.is_connected_to_shared_instance) }}
            </strong>
          </div>
        </div>
      </header>

      <div class="about-grid">
        <aside class="panel about-rail">
          <div class="panel-header">
            <div>
              <div class="panel-title">Identity</div>
              <div class="panel-subtitle">Primary process metadata</div>
            </div>
          </div>

          <div class="mono-tag">
            {{ formatValue(appInfo?.reticulum_destination) }}
          </div>

          <div class="rail-rows">
            <div class="rail-row" v-for="entry in overviewRows" :key="entry.label">
              <span>{{ entry.label }}</span>
              <strong>{{ entry.value }}</strong>
            </div>
          </div>

          <div class="rail-footer">
            <div class="panel-subtitle">Runtime Engines</div>
            <div class="engine-pills">
              <span class="engine-pill">RNS {{ formatValue(appInfo?.rns_version) }}</span>
              <span class="engine-pill">LXMF {{ formatValue(appInfo?.lxmf_version) }}</span>
            </div>
          </div>
        </aside>

        <section class="panel about-main">
          <div class="panel-header">
            <div>
              <div class="panel-title">Runtime Profile</div>
              <div class="panel-subtitle">Service health and resource references</div>
            </div>
            <div class="panel-tabs">
              <button class="panel-tab" :class="{ active: resourcesTab === 'help' }" type="button" @click="resourcesTab = 'help'">
                Help
              </button>
              <button
                class="panel-tab"
                :class="{ active: resourcesTab === 'examples' }"
                type="button"
                @click="resourcesTab = 'examples'"
              >
                Examples
              </button>
            </div>
          </div>

          <div class="card-grid">
            <article class="data-card">
              <div class="card-title">Runtime Status</div>
              <div class="row-grid">
                <div class="row-item" v-for="entry in runtimeRows" :key="entry.label">
                  <span>{{ entry.label }}</span>
                  <strong>{{ entry.value }}</strong>
                </div>
              </div>
            </article>

            <article class="data-card">
              <div class="card-title">Storage Paths</div>
              <div v-if="storageRows.length" class="row-grid">
                <div class="row-item row-item--stack" v-for="entry in storageRows" :key="entry.label">
                  <span>{{ entry.label }}</span>
                  <strong class="mono">{{ entry.value }}</strong>
                </div>
              </div>
              <div v-else class="panel-empty">Storage paths are not available.</div>
            </article>
          </div>

          <div class="resource-panel">
            <div v-if="resourcesTab === 'help'" class="doc-links">
              <RouterLink
                v-for="screen in helpScreens"
                :key="screen.path"
                class="doc-link"
                :to="{ path: screen.path, query: { help: '1' } }"
              >
                <span>{{ screen.title }}</span>
                <small>{{ screen.path }} - {{ screen.fileName }}</small>
              </RouterLink>
            </div>

            <div v-else class="resource-output">
              <div class="resource-section">
                <div class="resource-section__title">Commands</div>
                <BaseFormattedOutput v-if="commandsContent" :value="commandsContent" mode="markdown" />
                <div v-else class="panel-empty">Load commands to view command references.</div>
              </div>
              <div class="resource-section">
                <div class="resource-section__title">Examples</div>
                <BaseFormattedOutput v-if="examplesContent" :value="examplesContent" mode="markdown" />
                <div v-else class="panel-empty">Load examples to view command references.</div>
              </div>
              <div class="panel-actions">
                <BaseButton variant="secondary" icon-left="help" @click="loadCommands">Load Commands</BaseButton>
                <BaseButton variant="secondary" icon-left="list" @click="loadExamples">Load Examples</BaseButton>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { storeToRefs } from "pinia";
import BaseButton from "../components/BaseButton.vue";
import BaseFormattedOutput from "../components/BaseFormattedOutput.vue";
import { endpoints } from "../api/endpoints";
import { get } from "../api/client";
import { useAppStore } from "../stores/app";
import { HELP_SCREENS } from "../utils/online-help";

const appStore = useAppStore();
const { appInfo } = storeToRefs(appStore);
const commandsContent = ref<string | null>(null);
const examplesContent = ref<string | null>(null);
const resourcesTab = ref<"help" | "examples">("help");
const helpScreens = HELP_SCREENS;

const formatValue = (value: unknown) => {
  if (value === null || value === undefined) {
    return "-";
  }
  if (typeof value === "string") {
    return value.trim() ? value : "-";
  }
  if (typeof value === "number") {
    return Number.isFinite(value) ? value.toString() : "-";
  }
  return String(value);
};

const formatFlag = (value?: boolean | null) => {
  if (value === null || value === undefined) {
    return "-";
  }
  return value ? "Enabled" : "Disabled";
};

const formatStorageKey = (key: string) => {
  const labels: Record<string, string> = {
    storage: "Storage root",
    database: "Database",
    reticulum_config: "Reticulum config",
    files: "Files",
    images: "Images"
  };
  if (labels[key]) {
    return labels[key];
  }
  return key
    .replace(/[_-]+/g, " ")
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase());
};

const overviewRows = computed(() => [
  { label: "Name", value: formatValue(appInfo.value?.name) },
  { label: "Description", value: formatValue(appInfo.value?.description) }
]);

const runtimeRows = computed(() => [
  { label: "Reticulum", value: formatValue(appInfo.value?.rns_version) },
  { label: "LXMF", value: formatValue(appInfo.value?.lxmf_version) },
  { label: "Transport", value: formatFlag(appInfo.value?.is_transport_enabled) },
  { label: "Shared Instance", value: formatFlag(appInfo.value?.is_connected_to_shared_instance) },
  { label: "Destination", value: formatValue(appInfo.value?.reticulum_destination) }
]);

const storageRows = computed(() => {
  const rows = appInfo.value?.storage_paths;
  if (!rows) {
    return [];
  }
  return Object.entries(rows).map(([key, value]) => ({
    label: formatStorageKey(key),
    value: formatValue(value)
  }));
});

const loadCommands = async () => {
  const response = await get<unknown>(endpoints.help);
  commandsContent.value = typeof response === "string" ? response : JSON.stringify(response, null, 2);
};

const loadExamples = async () => {
  const response = await get<unknown>(endpoints.examples);
  examplesContent.value = typeof response === "string" ? response : JSON.stringify(response, null, 2);
};

onMounted(async () => {
  await appStore.fetchAppInfo();
});
</script>

<style scoped src="./styles/AboutPage.css"></style>



