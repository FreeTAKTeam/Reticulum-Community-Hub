<template>
  <div class="space-y-6">
    <BaseCard title="Configuration">
      <div class="mb-4 flex flex-wrap gap-2">
        <BaseButton variant="secondary" @click="loadConfig">Load</BaseButton>
        <BaseButton variant="secondary" @click="validateConfig">Validate</BaseButton>
        <BaseButton @click="applyConfig">Apply</BaseButton>
        <BaseButton variant="ghost" @click="rollbackConfig">Rollback</BaseButton>
      </div>
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
    </BaseCard>

    <BaseCard title="Tools">
      <div class="flex flex-wrap gap-2">
        <BaseButton variant="secondary" @click="runTool('Ping')">Ping</BaseButton>
        <BaseButton variant="secondary" @click="runTool('DumpRouting')">Dump Routing</BaseButton>
        <BaseButton variant="secondary" @click="runTool('ListClients')">List Clients</BaseButton>
        <BaseButton variant="secondary" @click="loadHelp">Help</BaseButton>
        <BaseButton variant="secondary" @click="loadExamples">Examples</BaseButton>
      </div>
      <BaseFormattedOutput v-if="toolResponse" class="mt-4" :value="toolResponse" :mode="toolResponseMode" />
    </BaseCard>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
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

const loadHelp = async () => {
  const response = await get<unknown>(endpoints.help);
  setResponse(response, "markdown");
};

const loadExamples = async () => {
  const response = await get<unknown>(endpoints.examples);
  if (typeof response === "string") {
    setResponse(response, "markdown");
    return;
  }
  setResponse(response, "auto");
};

const setResponse = (response: unknown, mode: "auto" | "markdown" | "json" | "html") => {
  toolResponse.value = response;
  toolResponseMode.value = mode;
};
</script>
