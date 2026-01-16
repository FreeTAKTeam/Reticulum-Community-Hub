<template>
  <div class="space-y-6">
    <BaseCard title="App Info">
      <div class="space-y-2 text-sm text-rth-muted">
        <div>Name: {{ appInfo?.name }}</div>
        <div>Version: {{ appInfo?.version }}</div>
        <div>Description: {{ appInfo?.description }}</div>
        <div>RNS: {{ appInfo?.rns_version }}</div>
        <div>LXMF: {{ appInfo?.lxmf_version }}</div>
      </div>
    </BaseCard>

    <BaseCard title="Storage Paths">
      <div v-if="appInfo?.storage_paths" class="space-y-2 text-sm text-rth-muted">
        <div v-for="(value, key) in appInfo.storage_paths" :key="key">{{ key }}: {{ value }}</div>
      </div>
    </BaseCard>

    <BaseCard title="Documentation">
      <ul class="list-disc space-y-2 pl-5 text-sm text-rth-muted">
        <li><a class="text-rth-accent hover:underline" href="/docs/" target="_blank" rel="noreferrer">Project Docs</a></li>
        <li><a class="text-rth-accent hover:underline" href="/API/ReticulumCommunityHub-OAS.yaml" target="_blank" rel="noreferrer">OpenAPI Reference</a></li>
      </ul>
    </BaseCard>

    <BaseCard title="Help & Examples">
      <BaseFormattedOutput v-if="helpContent" class="mt-4" :value="helpContent" mode="markdown" />
      <BaseFormattedOutput v-if="examplesContent" class="mt-4" :value="examplesContent" mode="markdown" />
      <div v-if="!helpContent && !examplesContent" class="text-xs text-rth-muted">Load help or examples to view command references.</div>
      <div class="mt-4 flex flex-wrap justify-end gap-2">
        <BaseButton variant="secondary" icon-left="help" @click="loadHelp">Help</BaseButton>
        <BaseButton variant="secondary" icon-left="list" @click="loadExamples">Examples</BaseButton>
      </div>
    </BaseCard>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from "vue";
import { ref } from "vue";
import BaseButton from "../components/BaseButton.vue";
import BaseCard from "../components/BaseCard.vue";
import BaseFormattedOutput from "../components/BaseFormattedOutput.vue";
import { endpoints } from "../api/endpoints";
import { get } from "../api/client";
import type { AppInfo } from "../api/types";

const appInfo = ref<AppInfo | null>(null);
const helpContent = ref<string | null>(null);
const examplesContent = ref<string | null>(null);

const loadHelp = async () => {
  const response = await get<unknown>(endpoints.help);
  helpContent.value = typeof response === "string" ? response : JSON.stringify(response, null, 2);
};

const loadExamples = async () => {
  const response = await get<unknown>(endpoints.examples);
  examplesContent.value = typeof response === "string" ? response : JSON.stringify(response, null, 2);
};

onMounted(async () => {
  appInfo.value = await get<AppInfo>(endpoints.appInfo);
});
</script>
