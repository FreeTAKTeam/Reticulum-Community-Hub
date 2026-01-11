<template>
  <div class="space-y-6">
    <BaseCard title="App Info">
      <div class="space-y-2 text-sm text-slate-300">
        <div>Name: {{ appInfo?.name }}</div>
        <div>Version: {{ appInfo?.version }}</div>
        <div>Description: {{ appInfo?.description }}</div>
        <div>RNS: {{ appInfo?.rns_version }}</div>
        <div>LXMF: {{ appInfo?.lxmf_version }}</div>
      </div>
    </BaseCard>

    <BaseCard title="Storage Paths">
      <div v-if="appInfo?.storage_paths" class="space-y-2 text-sm text-slate-300">
        <div v-for="(value, key) in appInfo.storage_paths" :key="key">{{ key }}: {{ value }}</div>
      </div>
    </BaseCard>

    <BaseCard title="Documentation">
      <ul class="list-disc space-y-2 pl-5 text-sm text-slate-300">
        <li><a class="text-sky-300 hover:underline" href="/docs/" target="_blank" rel="noreferrer">Project Docs</a></li>
        <li><a class="text-sky-300 hover:underline" href="/API/ReticulumTelemetryHub-OAS.yaml" target="_blank" rel="noreferrer">OpenAPI Reference</a></li>
      </ul>
    </BaseCard>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from "vue";
import { ref } from "vue";
import BaseCard from "../components/BaseCard.vue";
import { endpoints } from "../api/endpoints";
import { get } from "../api/client";
import type { AppInfo } from "../api/types";

const appInfo = ref<AppInfo | null>(null);

onMounted(async () => {
  appInfo.value = await get<AppInfo>(endpoints.appInfo);
});
</script>
