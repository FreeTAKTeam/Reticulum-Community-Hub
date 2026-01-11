<template>
  <div class="space-y-6">
    <BaseCard title="Configuration">
      <div class="mb-4 flex flex-wrap gap-2">
        <BaseButton variant="secondary" @click="configStore.loadConfig">Load</BaseButton>
        <BaseButton variant="secondary" @click="configStore.validateConfig">Validate</BaseButton>
        <BaseButton @click="configStore.applyConfig">Apply</BaseButton>
        <BaseButton variant="ghost" @click="configStore.rollbackConfig">Rollback</BaseButton>
      </div>
      <textarea v-model="configStore.configText" class="h-64 w-full rounded border border-rth-border bg-slate-900 p-3 text-xs text-slate-200"></textarea>
      <div class="mt-4 space-y-3 text-xs text-slate-300">
        <div v-if="configStore.validation">Validation: {{ configStore.validation }}</div>
        <div v-if="configStore.applyResult">Apply result: {{ configStore.applyResult }}</div>
        <div v-if="configStore.rollbackResult">Rollback result: {{ configStore.rollbackResult }}</div>
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
      <pre v-if="toolResponse" class="mt-4 max-h-80 overflow-auto rounded bg-slate-900 p-3 text-xs text-slate-200">{{ toolResponse }}</pre>
    </BaseCard>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import BaseButton from "../components/BaseButton.vue";
import BaseCard from "../components/BaseCard.vue";
import { endpoints } from "../api/endpoints";
import { get } from "../api/client";
import { useConfigStore } from "../stores/config";

const configStore = useConfigStore();
const toolResponse = ref("");

const runTool = async (command: string) => {
  toolResponse.value = await get<string>(`${endpoints.command}/${command}`);
};

const loadHelp = async () => {
  toolResponse.value = await get<string>(endpoints.help);
};

const loadExamples = async () => {
  toolResponse.value = await get<string>(endpoints.examples);
};
</script>
