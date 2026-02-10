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

<style scoped>
.about-cosmos {
  --neon: #37f2ff;
  --panel-dark: rgba(4, 12, 22, 0.96);
  --panel-light: rgba(10, 30, 45, 0.94);
  --amber: #ffb35c;
  color: #dffcff;
  font-family: "Orbitron", "Rajdhani", "Barlow", sans-serif;
}

.about-shell {
  position: relative;
  padding: 20px 22px 24px;
  border-radius: 18px;
  border: 1px solid rgba(55, 242, 255, 0.25);
  background: radial-gradient(circle at top, rgba(42, 210, 255, 0.12), transparent 56%),
    linear-gradient(145deg, rgba(5, 16, 28, 0.96), rgba(2, 6, 12, 0.98));
  box-shadow: 0 18px 55px rgba(1, 6, 12, 0.65), inset 0 0 0 1px rgba(55, 242, 255, 0.08);
  overflow: hidden;
}

.about-shell::before {
  content: "";
  position: absolute;
  inset: 0;
  background: radial-gradient(circle at 1px 1px, rgba(55, 242, 255, 0.08) 1px, transparent 0) 0 0 / 18px 18px;
  opacity: 0.58;
  pointer-events: none;
}

.about-top {
  position: relative;
  z-index: 1;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 14px;
  margin-bottom: 16px;
}

.about-title {
  font-size: 20px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #d4fbff;
  text-shadow: 0 0 12px rgba(55, 242, 255, 0.5);
}

.about-subtitle {
  margin-top: 6px;
  font-family: "Rajdhani", "Barlow", sans-serif;
  font-size: 12px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: rgba(209, 251, 255, 0.7);
}

.about-badges {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 10px;
}

.about-badge {
  min-width: 130px;
  padding: 8px 10px;
  border: 1px solid rgba(55, 242, 255, 0.26);
  background: rgba(6, 18, 28, 0.8);
  clip-path: polygon(9px 0, 100% 0, calc(100% - 9px) 100%, 0 100%);
  display: grid;
  gap: 4px;
}

.about-badge span {
  font-size: 10px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: rgba(206, 250, 255, 0.62);
}

.about-badge strong {
  font-size: 12px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: #e8feff;
}

.about-grid {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: minmax(240px, 300px) 1fr;
  gap: 16px;
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

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 14px;
}

.panel-title {
  font-size: 16px;
  text-transform: uppercase;
  letter-spacing: 0.16em;
  color: #d1fbff;
}

.panel-subtitle {
  margin-top: 4px;
  font-family: "Rajdhani", "Barlow", sans-serif;
  font-size: 11px;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: rgba(209, 251, 255, 0.64);
}

.about-rail {
  display: grid;
  align-content: start;
  gap: 12px;
}

.mono-tag {
  border: 1px solid rgba(255, 179, 92, 0.46);
  background: rgba(14, 24, 30, 0.62);
  border-radius: 10px;
  padding: 10px;
  font-family: "JetBrains Mono", "Cascadia Mono", monospace;
  font-size: 11px;
  letter-spacing: 0.05em;
  color: #ffe5c2;
  overflow-wrap: anywhere;
}

.rail-rows {
  display: grid;
  gap: 8px;
}

.rail-row {
  border: 1px solid rgba(55, 242, 255, 0.2);
  background: rgba(7, 18, 28, 0.65);
  border-radius: 10px;
  padding: 8px 10px;
  display: grid;
  gap: 4px;
}

.rail-row span {
  font-size: 10px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: rgba(208, 250, 255, 0.58);
}

.rail-row strong {
  font-family: "Rajdhani", "Barlow", sans-serif;
  font-size: 13px;
  color: #e4feff;
}

.rail-footer {
  border-top: 1px solid rgba(55, 242, 255, 0.18);
  padding-top: 10px;
}

.engine-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}

.engine-pill {
  border: 1px solid rgba(55, 242, 255, 0.28);
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.16em;
  color: rgba(225, 253, 255, 0.86);
  background: rgba(6, 16, 24, 0.72);
}

.state-ok {
  color: #8cf2d6;
}

.state-warn {
  color: #ffd9a9;
}

.state-idle {
  color: #d4faff;
}

.about-main {
  min-height: 560px;
}

.panel-tabs {
  display: inline-flex;
  background: rgba(7, 18, 26, 0.8);
  border: 1px solid rgba(55, 242, 255, 0.25);
  border-radius: 999px;
  padding: 4px;
  gap: 4px;
}

.panel-tab {
  border: 1px solid transparent;
  background: transparent;
  color: rgba(209, 251, 255, 0.62);
  padding: 6px 14px;
  border-radius: 999px;
  text-transform: uppercase;
  letter-spacing: 0.16em;
  font-size: 11px;
  transition: all 0.2s ease;
}

.panel-tab.active {
  background: rgba(55, 242, 255, 0.12);
  border-color: rgba(55, 242, 255, 0.6);
  color: #e0feff;
  box-shadow: 0 0 14px rgba(55, 242, 255, 0.25);
}

.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 12px;
}

.data-card {
  border: 1px solid rgba(55, 242, 255, 0.24);
  background: rgba(7, 18, 28, 0.72);
  border-radius: 12px;
  padding: 12px;
}

.card-title {
  font-size: 11px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: rgba(201, 248, 255, 0.85);
  margin-bottom: 10px;
}

.row-grid {
  display: grid;
  gap: 8px;
}

.row-item {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.row-item:last-child {
  padding-bottom: 0;
  border-bottom: none;
}

.row-item span {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  color: rgba(200, 248, 255, 0.58);
}

.row-item strong {
  font-family: "Rajdhani", "Barlow", sans-serif;
  font-size: 13px;
  color: #e7fdff;
  text-align: right;
}

.row-item--stack {
  flex-direction: column;
  gap: 4px;
}

.row-item--stack strong {
  text-align: left;
}

.resource-panel {
  margin-top: 14px;
  border: 1px solid rgba(55, 242, 255, 0.24);
  background: rgba(6, 16, 26, 0.78);
  border-radius: 12px;
  padding: 12px;
}

.doc-links {
  display: grid;
  gap: 10px;
}

.doc-link {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  border: 1px solid rgba(55, 242, 255, 0.24);
  border-radius: 10px;
  padding: 10px 12px;
  color: #e6feff;
  background: rgba(8, 20, 30, 0.8);
  transition: all 0.2s ease;
}

.doc-link:hover {
  border-color: rgba(55, 242, 255, 0.52);
  box-shadow: 0 0 14px rgba(55, 242, 255, 0.2);
}

.doc-link span {
  text-transform: uppercase;
  letter-spacing: 0.14em;
  font-size: 11px;
}

.doc-link small {
  font-family: "JetBrains Mono", "Cascadia Mono", monospace;
  font-size: 11px;
  color: rgba(201, 248, 255, 0.65);
}

.resource-output {
  display: grid;
  gap: 10px;
}

.resource-section {
  display: grid;
  gap: 8px;
}

.resource-section__title {
  text-transform: uppercase;
  letter-spacing: 0.16em;
  font-size: 11px;
  color: rgba(201, 248, 255, 0.75);
}

.panel-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.panel-empty {
  border: 1px dashed rgba(55, 242, 255, 0.3);
  border-radius: 10px;
  padding: 14px;
  text-align: center;
  text-transform: uppercase;
  letter-spacing: 0.16em;
  font-size: 11px;
  color: rgba(209, 251, 255, 0.62);
}

.mono {
  font-family: "JetBrains Mono", "Cascadia Mono", monospace;
}

:deep(.about-cosmos .cui-btn) {
  background: linear-gradient(135deg, rgba(35, 130, 160, 0.45), rgba(6, 18, 28, 0.92));
  border: 1px solid rgba(55, 242, 255, 0.45);
  color: #e5feff;
  text-transform: uppercase;
  letter-spacing: 0.18em;
  font-size: 10px;
  padding: 6px 12px;
  box-shadow: 0 0 12px rgba(55, 242, 255, 0.15);
}

:deep(.about-cosmos .cui-btn--secondary) {
  background: linear-gradient(135deg, rgba(14, 44, 60, 0.85), rgba(6, 14, 22, 0.92));
}

@media (max-width: 1120px) {
  .about-grid {
    grid-template-columns: 1fr;
  }

  .about-main {
    min-height: 0;
  }
}

@media (max-width: 760px) {
  .about-top {
    flex-direction: column;
  }

  .about-badges {
    justify-content: flex-start;
  }

  .panel-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .panel-tabs {
    align-self: flex-start;
  }
}
</style>

