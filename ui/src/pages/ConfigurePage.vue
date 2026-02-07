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

<style scoped>
.configure-console {
  --neon: #37f2ff;
  --neon-soft: rgba(55, 242, 255, 0.35);
  --panel-dark: rgba(4, 12, 22, 0.96);
  --panel-light: rgba(10, 30, 45, 0.94);
  --amber: #ffb35c;
  --danger: rgba(255, 114, 114, 0.9);
  color: #dffcff;
  font-family: "Orbitron", "Rajdhani", "Barlow", sans-serif;
}

.configure-shell {
  position: relative;
  padding: 18px 20px 24px;
  border-radius: 18px;
  border: 1px solid rgba(55, 242, 255, 0.25);
  background: radial-gradient(circle at top, rgba(42, 210, 255, 0.11), transparent 58%),
    linear-gradient(145deg, rgba(5, 16, 28, 0.96), rgba(2, 6, 12, 0.98));
  box-shadow: 0 18px 55px rgba(1, 6, 12, 0.62), inset 0 0 0 1px rgba(55, 242, 255, 0.08);
  overflow: hidden;
}

.configure-shell::before {
  content: "";
  position: absolute;
  inset: 0;
  background: radial-gradient(circle at 1px 1px, rgba(55, 242, 255, 0.08) 1px, transparent 0) 0 0 / 18px 18px;
  opacity: 0.55;
  pointer-events: none;
}

.configure-top {
  position: relative;
  z-index: 1;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 16px;
}

.configure-title {
  font-size: 20px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #d4fbff;
  text-shadow: 0 0 12px rgba(55, 242, 255, 0.45);
}

.configure-subtitle {
  margin-top: 5px;
  font-family: "Rajdhani", "Barlow", sans-serif;
  font-size: 12px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: rgba(206, 250, 255, 0.7);
}

.configure-pills {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 10px;
}

.configure-pill {
  min-width: 138px;
  padding: 8px 10px;
  border: 1px solid rgba(55, 242, 255, 0.28);
  background: rgba(6, 18, 28, 0.78);
  clip-path: polygon(8px 0, 100% 0, calc(100% - 8px) 100%, 0 100%);
  display: grid;
  gap: 3px;
}

.configure-pill span {
  font-size: 10px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: rgba(206, 250, 255, 0.6);
}

.configure-pill strong {
  font-size: 12px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: #e8feff;
}

.configure-grid {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: minmax(230px, 280px) 1fr;
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
  font-size: 15px;
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
  color: rgba(209, 251, 255, 0.6);
}

.configure-rail {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.rail-tabs {
  display: grid;
  gap: 8px;
}

.rail-tab {
  border: 1px solid rgba(55, 242, 255, 0.22);
  background: rgba(7, 18, 28, 0.62);
  color: rgba(213, 251, 255, 0.92);
  padding: 10px 12px;
  border-radius: 10px;
  text-align: left;
  transition: all 0.2s ease;
  display: grid;
  gap: 2px;
}

.rail-tab span {
  text-transform: uppercase;
  letter-spacing: 0.14em;
  font-size: 11px;
}

.rail-tab small {
  text-transform: uppercase;
  letter-spacing: 0.1em;
  font-size: 10px;
  color: rgba(213, 251, 255, 0.58);
}

.rail-tab:hover {
  border-color: rgba(55, 242, 255, 0.45);
}

.rail-tab.active {
  border-color: rgba(55, 242, 255, 0.7);
  background: rgba(55, 242, 255, 0.13);
  box-shadow: 0 0 16px rgba(55, 242, 255, 0.24);
}

.rail-stats {
  margin-top: auto;
  border: 1px solid rgba(55, 242, 255, 0.22);
  background: rgba(6, 15, 24, 0.76);
  border-radius: 10px;
  padding: 10px;
  display: grid;
  gap: 8px;
}

.rail-stat {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  font-family: "Rajdhani", "Barlow", sans-serif;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  font-size: 11px;
}

.rail-stat span {
  color: rgba(208, 250, 255, 0.58);
}

.rail-stat strong {
  color: #dffeff;
}

.state-idle {
  color: #dffeff;
}

.state-ok {
  color: #8cf2d6;
}

.state-danger {
  color: #ffc8c8;
}

.configure-main {
  min-height: 620px;
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

.content-stack,
.tools-stack,
.reticulum-stack {
  display: grid;
  gap: 14px;
}

.focus-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
  gap: 12px;
}

.focus-card,
.reticulum-banner,
.tools-hud {
  border: 1px solid rgba(55, 242, 255, 0.24);
  background: rgba(8, 20, 31, 0.76);
  border-radius: 12px;
  padding: 12px 14px;
  display: grid;
  gap: 5px;
}

.focus-card--hint {
  border-color: rgba(255, 179, 92, 0.34);
  box-shadow: inset 0 0 12px rgba(255, 179, 92, 0.08);
}

.focus-kicker {
  font-size: 10px;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: rgba(198, 246, 255, 0.62);
}

.focus-title {
  font-size: 14px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: #e6feff;
}

.focus-copy {
  margin: 0;
  font-family: "Rajdhani", "Barlow", sans-serif;
  font-size: 12px;
  line-height: 1.4;
  color: rgba(222, 251, 255, 0.75);
}

.editor-block {
  border: 1px solid rgba(55, 242, 255, 0.25);
  background: rgba(7, 18, 28, 0.8);
  border-radius: 12px;
  padding: 12px;
  display: grid;
  gap: 10px;
}

.editor-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 10px;
}

.editor-title {
  font-size: 12px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: #d9fdff;
}

.editor-subtitle {
  margin-top: 3px;
  font-family: "Rajdhani", "Barlow", sans-serif;
  font-size: 11px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: rgba(198, 246, 255, 0.6);
}

.editor-size {
  font-size: 11px;
  letter-spacing: 0.08em;
  color: rgba(198, 246, 255, 0.8);
}

.config-textarea {
  width: 100%;
  min-height: 310px;
  resize: vertical;
  border: 1px solid rgba(55, 242, 255, 0.3);
  border-radius: 10px;
  background: linear-gradient(180deg, rgba(8, 22, 34, 0.95), rgba(5, 15, 24, 0.98));
  color: #dffcff;
  padding: 12px;
  font-family: "JetBrains Mono", "Cascadia Mono", monospace;
  font-size: 12px;
  line-height: 1.45;
}

.config-textarea:focus {
  outline: none;
  border-color: rgba(55, 242, 255, 0.66);
  box-shadow: 0 0 16px rgba(55, 242, 255, 0.22);
}

.response-grid {
  display: grid;
  gap: 10px;
}

.response-card {
  border: 1px solid rgba(55, 242, 255, 0.24);
  background: rgba(6, 16, 26, 0.84);
  border-radius: 10px;
  padding: 10px 12px;
}

.response-card--danger {
  border-color: rgba(255, 114, 114, 0.5);
  box-shadow: inset 0 0 14px rgba(255, 114, 114, 0.09);
}

.response-title {
  font-size: 10px;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: rgba(199, 247, 255, 0.7);
  margin-bottom: 8px;
}

.response-copy {
  font-family: "Rajdhani", "Barlow", sans-serif;
  font-size: 12px;
  color: #ffd8d8;
}

.response-empty {
  border: 1px dashed rgba(55, 242, 255, 0.28);
  border-radius: 10px;
  padding: 14px;
  text-align: center;
  text-transform: uppercase;
  letter-spacing: 0.16em;
  font-size: 11px;
  color: rgba(209, 251, 255, 0.62);
}

.panel-actions,
.tool-actions {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 10px;
}

.mono {
  font-family: "JetBrains Mono", "Cascadia Mono", monospace;
}

:deep(.configure-console .cui-btn) {
  background: linear-gradient(135deg, rgba(35, 130, 160, 0.45), rgba(6, 18, 28, 0.92));
  border: 1px solid rgba(55, 242, 255, 0.45);
  color: #e5feff;
  text-transform: uppercase;
  letter-spacing: 0.18em;
  font-size: 10px;
  padding: 6px 12px;
  box-shadow: 0 0 12px rgba(55, 242, 255, 0.15);
}

:deep(.configure-console .cui-btn--secondary) {
  background: linear-gradient(135deg, rgba(14, 44, 60, 0.85), rgba(6, 14, 22, 0.92));
}

:deep(.response-output) {
  margin-top: 0;
}

:deep(.response-output > div) {
  max-height: 260px;
}

:deep(.reticulum-stack .cui-panel) {
  border-color: rgba(55, 242, 255, 0.25);
}

:deep(.reticulum-stack .rounded.border-rth-border.bg-rth-panel-muted) {
  border-color: rgba(55, 242, 255, 0.24);
  background: rgba(8, 20, 31, 0.8);
}

@media (max-width: 1120px) {
  .configure-grid {
    grid-template-columns: 1fr;
  }

  .configure-main {
    min-height: 0;
  }
}

@media (max-width: 760px) {
  .configure-top {
    flex-direction: column;
    align-items: flex-start;
  }

  .configure-pills {
    justify-content: flex-start;
  }

  .panel-header {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
