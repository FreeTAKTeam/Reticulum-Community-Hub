<template>
  <div class="space-y-6">
    <BaseCard title="Configuration & Tools">
      <div class="mb-4 cui-tab-group">
        <BaseButton
          variant="tab"
          icon-left="settings"
          :class="{ 'cui-tab-active': activeTab === 'config' }"
          @click="activeTab = 'config'"
        >
          Configuration
        </BaseButton>
        <BaseButton
          variant="tab"
          icon-left="layers"
          :class="{ 'cui-tab-active': activeTab === 'reticulum' }"
          @click="activeTab = 'reticulum'"
        >
          Reticulum
        </BaseButton>
        <BaseButton
          variant="tab"
          icon-left="tool"
          :class="{ 'cui-tab-active': activeTab === 'tools' }"
          @click="activeTab = 'tools'"
        >
          Tools
        </BaseButton>
      </div>
      <div v-if="activeTab === 'config'">
        <div class="mb-4 rounded border border-rth-border bg-rth-panel-muted p-3">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div class="text-[10px] uppercase tracking-[0.2em] text-rth-muted">WebMap</div>
              <div class="text-sm font-semibold text-rth-text">Marker Labels</div>
              <div class="text-xs text-rth-muted">Show names next to telemetry and operator markers.</div>
            </div>
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
          </div>
        </div>
        <textarea
          v-model="configStore.configText"
          class="h-64 w-full rounded border border-rth-border bg-rth-panel-muted p-3 text-xs text-rth-text"
        ></textarea>
        <div class="mt-4 space-y-3 text-xs text-rth-muted">
          <div v-if="configStore.error" class="text-[#fecaca]">Error: {{ configStore.error }}</div>
          <div v-if="configStore.validation">
            <div class="text-xs text-rth-muted">Validation</div>
            <BaseFormattedOutput class="mt-2" :value="configStore.validation" />
          </div>
          <div v-if="configStore.applyResult">
            <div class="text-xs text-rth-muted">Apply result</div>
            <BaseFormattedOutput class="mt-2" :value="configStore.applyResult" />
          </div>
          <div v-if="configStore.rollbackResult">
            <div class="text-xs text-rth-muted">Rollback result</div>
            <BaseFormattedOutput class="mt-2" :value="configStore.rollbackResult" />
          </div>
        </div>
        <div class="mt-4 flex flex-wrap justify-end gap-2">
          <BaseButton variant="secondary" icon-left="upload" @click="loadConfig">Load</BaseButton>
          <BaseButton variant="secondary" icon-left="check" @click="validateConfig">Validate</BaseButton>
          <BaseButton icon-left="check" @click="applyConfig">Apply</BaseButton>
          <BaseButton variant="secondary" icon-left="undo" @click="rollbackConfig">Rollback</BaseButton>
        </div>
      </div>
      <div v-else-if="activeTab === 'reticulum'">
        <ReticulumConfigEditor />
      </div>
      <div v-else>
        <BaseFormattedOutput v-if="toolResponse" class="mt-4" :value="toolResponse" :mode="toolResponseMode" />
        <div v-else class="text-xs text-rth-muted">Run a tool to see the response.</div>
        <div class="mt-4 flex flex-wrap justify-end gap-2">
          <BaseButton variant="secondary" icon-left="send" @click="runTool('Ping')">Ping</BaseButton>
          <BaseButton variant="secondary" icon-left="route" @click="runTool('DumpRouting')">Dump Routing</BaseButton>
          <BaseButton variant="secondary" icon-left="users" @click="runTool('ListClients')">List Clients</BaseButton>
        </div>
      </div>
    </BaseCard>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import BaseButton from "../components/BaseButton.vue";
import BaseCard from "../components/BaseCard.vue";
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
const markerLabelsEnabled = computed({
  get: () => mapSettingsStore.showMarkerLabels,
  set: (value: boolean) => {
    mapSettingsStore.setShowMarkerLabels(value);
  }
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
