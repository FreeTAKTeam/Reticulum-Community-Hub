<template>
  <div class="space-y-6">
    <BaseCard title="Configuration & Tools">
      <div class="mb-4 flex flex-wrap gap-2">
        <BaseButton variant="tab" icon-left="settings" :class="{ 'cui-tab-active': activeTab === 'config' }" @click="activeTab = 'config'">
          Configuration
        </BaseButton>
        <BaseButton variant="tab" icon-left="tool" :class="{ 'cui-tab-active': activeTab === 'tools' }" @click="activeTab = 'tools'">
          Tools
        </BaseButton>
      </div>
      <div v-if="activeTab === 'config'">
        <textarea v-model="configStore.configText" class="h-64 w-full rounded border border-rth-border bg-rth-panel-muted p-3 text-xs text-rth-text"></textarea>
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
import { onMounted, ref } from "vue";
import BaseButton from "../components/BaseButton.vue";
import BaseCard from "../components/BaseCard.vue";
import BaseFormattedOutput from "../components/BaseFormattedOutput.vue";
import { endpoints } from "../api/endpoints";
import { get } from "../api/client";
import { useConfigStore } from "../stores/config";
import { useToastStore } from "../stores/toasts";

const configStore = useConfigStore();
const toastStore = useToastStore();
const toolResponse = ref<unknown>(null);
const toolResponseMode = ref<"auto" | "markdown" | "json" | "html">("auto");
const activeTab = ref<"config" | "tools">("config");

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
