<template>
  <div class="configure-console">
    <div class="configure-shell">
      <header class="configure-top">
        <div>
          <div class="configure-title">Configuration Console</div>
          <div class="configure-subtitle">Hub controls, Reticulum runtime tuning, and command diagnostics</div>
        </div>
        <div class="configure-pills">
          <div class="configure-pill">
            <span>Active Module</span>
            <strong>{{ activeTabLabel }}</strong>
          </div>
          <div class="configure-pill">
            <span>Payload Size</span>
            <strong class="mono">{{ configSizeLabel }}</strong>
          </div>
        </div>
      </header>

      <div class="configure-grid">
        <aside class="panel configure-rail">
          <div class="panel-header">
            <div>
              <div class="panel-title">Command Rail</div>
              <div class="panel-subtitle">Select a control surface</div>
            </div>
          </div>
          <div class="rail-tabs">
            <button class="rail-tab" :class="{ active: activeTab === 'config' }" type="button" @click="activeTab = 'config'">
              <span>Configuration</span>
              <small>Hub file edits</small>
            </button>
            <button class="rail-tab" :class="{ active: activeTab === 'reticulum' }" type="button" @click="activeTab = 'reticulum'">
              <span>Reticulum</span>
              <small>Network stack profile</small>
            </button>
            <button class="rail-tab" :class="{ active: activeTab === 'tools' }" type="button" @click="activeTab = 'tools'">
              <span>Tools</span>
              <small>Live command probes</small>
            </button>
          </div>
          <div class="rail-stats">
            <div class="rail-stat">
              <span>Status</span>
              <strong :class="healthStateClass">{{ healthStateLabel }}</strong>
            </div>
            <div class="rail-stat">
              <span>Validation</span>
              <strong>{{ configStore.validation ? "Available" : "Pending" }}</strong>
            </div>
            <div class="rail-stat">
              <span>Tool Stream</span>
              <strong>{{ toolResponse ? "Captured" : "Idle" }}</strong>
            </div>
          </div>
        </aside>

        <section class="panel configure-main">
          <div class="panel-header">
            <div>
              <div class="panel-title">{{ activeTabLabel }}</div>
              <div class="panel-subtitle">Operational channel</div>
            </div>
            <div class="panel-tabs">
              <button class="panel-tab" :class="{ active: activeTab === 'config' }" type="button" @click="activeTab = 'config'">
                Config
              </button>
              <button
                class="panel-tab"
                :class="{ active: activeTab === 'reticulum' }"
                type="button"
                @click="activeTab = 'reticulum'"
              >
                Reticulum
              </button>
              <button class="panel-tab" :class="{ active: activeTab === 'tools' }" type="button" @click="activeTab = 'tools'">
                Tools
              </button>
            </div>
          </div>

          <div v-if="activeTab === 'config'" class="content-stack">
            <div class="focus-grid">
              <section class="focus-card">
                <div class="focus-kicker">WebMap</div>
                <div class="focus-title">Marker Labels</div>
                <p class="focus-copy">Show names next to telemetry and operator markers.</p>
                <label class="cui-switch">
                  <input
                    v-model="markerLabelsEnabled"
                    type="checkbox"
                    class="cui-switch__input"
                    aria-label="Show marker labels on the WebMap"
                  />
                  <span class="cui-switch__track">
                    <span class="cui-switch__indicator" aria-hidden="true"></span>
                  </span>
                  <span class="cui-switch__label">{{ markerLabelsEnabled ? "On" : "Off" }}</span>
                </label>
              </section>

              <section class="focus-card focus-card--hint">
                <div class="focus-kicker">Workflow</div>
                <div class="focus-title">Recommended Sequence</div>
                <p class="focus-copy">Load, validate, apply, then rollback only if telemetry health degrades.</p>
              </section>
            </div>

            <section class="editor-block">
              <div class="editor-head">
                <div>
                  <div class="editor-title">Hub Configuration Payload</div>
                  <div class="editor-subtitle">Direct text editor</div>
                </div>
                <div class="editor-size mono">{{ configSizeLabel }}</div>
              </div>
              <textarea
                v-model="configStore.configText"
                class="config-textarea"
                spellcheck="false"
                aria-label="Hub configuration text"
              ></textarea>
            </section>

            <section class="response-grid">
              <article v-if="configStore.error" class="response-card response-card--danger">
                <div class="response-title">Error</div>
                <div class="response-copy">{{ configStore.error }}</div>
              </article>
              <article v-if="configStore.validation" class="response-card">
                <div class="response-title">Validation</div>
                <BaseFormattedOutput class="response-output" :value="configStore.validation" />
              </article>
              <article v-if="configStore.applyResult" class="response-card">
                <div class="response-title">Apply Result</div>
                <BaseFormattedOutput class="response-output" :value="configStore.applyResult" />
              </article>
              <article v-if="configStore.rollbackResult" class="response-card">
                <div class="response-title">Rollback Result</div>
                <BaseFormattedOutput class="response-output" :value="configStore.rollbackResult" />
              </article>
              <div
                v-if="!configStore.error && !configStore.validation && !configStore.applyResult && !configStore.rollbackResult"
                class="response-empty"
              >
                No configuration output captured yet.
              </div>
            </section>

            <div class="panel-actions">
              <BaseButton variant="secondary" icon-left="upload" @click="loadConfig">Load</BaseButton>
              <BaseButton variant="secondary" icon-left="check" @click="validateConfig">Validate</BaseButton>
              <BaseButton icon-left="check" @click="applyConfig">Apply</BaseButton>
              <BaseButton variant="secondary" icon-left="undo" @click="rollbackConfig">Rollback</BaseButton>
            </div>
          </div>

          <div v-else-if="activeTab === 'reticulum'" class="reticulum-stack">
            <div class="reticulum-banner">
              <div class="focus-kicker">Reticulum Engine</div>
              <div class="focus-title">Network profile editor</div>
              <p class="focus-copy">Tune interfaces, logging, and routing settings for your current mission context.</p>
            </div>
            <ReticulumConfigEditor />
          </div>

          <div v-else class="tools-stack">
            <div class="tools-hud">
              <div class="focus-kicker">Diagnostics</div>
              <div class="focus-title">Command channel</div>
              <p class="focus-copy">Run live checks against the currently connected hub.</p>
            </div>
            <div class="tool-actions">
              <BaseButton variant="secondary" icon-left="send" @click="runTool('Ping')">Ping</BaseButton>
              <BaseButton variant="secondary" icon-left="route" @click="runTool('DumpRouting')">Dump Routing</BaseButton>
              <BaseButton variant="secondary" icon-left="users" @click="runTool('ListClients')">List Clients</BaseButton>
            </div>
            <section class="response-grid">
              <article class="response-card">
                <div class="response-title">Tool Output</div>
                <BaseFormattedOutput
                  v-if="toolResponse"
                  class="response-output"
                  :value="toolResponse"
                  :mode="toolResponseMode"
                />
                <div v-else class="response-empty">Run a tool command to see output.</div>
              </article>
            </section>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import BaseButton from "../components/BaseButton.vue";
import BaseFormattedOutput from "../components/BaseFormattedOutput.vue";
import ReticulumConfigEditor from "../components/ReticulumConfigEditor.vue";
import { endpoints } from "../api/endpoints";
import { get } from "../api/client";
import { useConfigStore } from "../stores/config";
import { useMapSettingsStore } from "../stores/map-settings";
import { useToastStore } from "../stores/toasts";

const configStore = useConfigStore();
const mapSettingsStore = useMapSettingsStore();
const toastStore = useToastStore();
const toolResponse = ref<unknown>(null);
const toolResponseMode = ref<"auto" | "markdown" | "json" | "html">("auto");
const activeTab = ref<"config" | "reticulum" | "tools">("config");
const textEncoder = new TextEncoder();
const markerLabelsEnabled = computed({
  get: () => mapSettingsStore.showMarkerLabels,
  set: (value: boolean) => {
    mapSettingsStore.setShowMarkerLabels(value);
  }
});
const activeTabLabel = computed(() => {
  if (activeTab.value === "reticulum") {
    return "Reticulum";
  }
  if (activeTab.value === "tools") {
    return "Tools";
  }
  return "Configuration";
});
const configSizeLabel = computed(() => {
  const bytes = textEncoder.encode(configStore.configText ?? "").length;
  return `${bytes.toLocaleString()} bytes`;
});
const healthStateLabel = computed(() => {
  if (configStore.error) {
    return "Attention";
  }
  if (configStore.applyResult) {
    return "Applied";
  }
  if (configStore.validation) {
    return "Verified";
  }
  return "Standby";
});
const healthStateClass = computed(() => {
  if (configStore.error) {
    return "state-danger";
  }
  if (configStore.applyResult || configStore.validation) {
    return "state-ok";
  }
  return "state-idle";
});

const toolPaths: Record<string, string> = {
  Ping: endpoints.status,
  DumpRouting: `${endpoints.command}/DumpRouting`,
  ListClients: endpoints.clients
};

const runTool = async (tool: keyof typeof toolPaths) => {
  const response = await get<unknown>(toolPaths[tool]);
  setResponse(response, "auto");
};

const loadConfig = async () => {
  try {
    await configStore.loadConfig();
    toastStore.push("Config loaded", "success");
  } catch (error) {
    toastStore.push("Unable to load config", "danger");
  }
};

const validateConfig = async () => {
  try {
    await configStore.validateConfig();
    toastStore.push("Validation complete", "success");
  } catch (error) {
    toastStore.push("Validation failed", "danger");
  }
};

const applyConfig = async () => {
  try {
    await configStore.applyConfig();
    toastStore.push("Config applied", "success");
  } catch (error) {
    toastStore.push("Apply failed", "danger");
  }
};

const rollbackConfig = async () => {
  try {
    await configStore.rollbackConfig();
    toastStore.push("Rollback complete", "warning");
  } catch (error) {
    toastStore.push("Rollback failed", "danger");
  }
};

const setResponse = (response: unknown, mode: "auto" | "markdown" | "json" | "html") => {
  toolResponse.value = response;
  toolResponseMode.value = mode;
};

onMounted(async () => {
  try {
    await configStore.loadConfig();
  } catch (error) {
    toastStore.push("Unable to load config", "danger");
  }
});
</script>

<style scoped src="./styles/ConfigurePage.css"></style>


