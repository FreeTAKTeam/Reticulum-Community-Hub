<template>
  <div class="space-y-6">
    <div class="grid gap-4 xl:grid-cols-2">
      <BaseCard title="App Overview">
        <div class="cui-json-output">
          <div class="cui-json-row">
            <div class="cui-json-key">Name</div>
            <div class="cui-json-value">{{ formatValue(appInfo?.name) }}</div>
          </div>
          <div class="cui-json-row">
            <div class="cui-json-key">Version</div>
            <div class="cui-json-value">{{ formatValue(appInfo?.version) }}</div>
          </div>
          <div class="cui-json-row">
            <div class="cui-json-key">Description</div>
            <div class="cui-json-value">{{ formatValue(appInfo?.description) }}</div>
          </div>
        </div>
      </BaseCard>

      <BaseCard title="Runtime Status">
        <div class="cui-json-output">
          <div class="cui-json-row">
            <div class="cui-json-key">Reticulum</div>
            <div class="cui-json-value">{{ formatValue(appInfo?.rns_version) }}</div>
          </div>
          <div class="cui-json-row">
            <div class="cui-json-key">LXMF</div>
            <div class="cui-json-value">{{ formatValue(appInfo?.lxmf_version) }}</div>
          </div>
          <div class="cui-json-row">
            <div class="cui-json-key">Transport</div>
            <div class="cui-json-value">{{ formatFlag(appInfo?.is_transport_enabled) }}</div>
          </div>
          <div class="cui-json-row">
            <div class="cui-json-key">Shared Instance</div>
            <div class="cui-json-value">{{ formatFlag(appInfo?.is_connected_to_shared_instance) }}</div>
          </div>
          <div class="cui-json-row">
            <div class="cui-json-key">Reticulum Destination</div>
            <div class="cui-json-value">{{ formatValue(appInfo?.reticulum_destination) }}</div>
          </div>
        </div>
      </BaseCard>
    </div>

    <BaseCard title="Storage Paths">
      <div v-if="appInfo?.storage_paths" class="cui-json-output">
        <div v-for="(value, key) in appInfo.storage_paths" :key="key" class="cui-json-row">
          <div class="cui-json-key">{{ formatStorageKey(key) }}</div>
          <div class="cui-json-value">{{ formatValue(value) }}</div>
        </div>
      </div>
      <div v-else class="text-xs text-rth-muted">Storage paths are not available.</div>
    </BaseCard>

    <div class="grid gap-4 lg:grid-cols-2">
      <BaseCard class="lg:col-span-2" title="Resources">
        <div class="mb-4 cui-tab-group">
          <BaseButton variant="tab" :class="{ 'cui-tab-active': resourcesTab === 'docs' }" @click="resourcesTab = 'docs'">
            Documentation
          </BaseButton>
          <BaseButton variant="tab" :class="{ 'cui-tab-active': resourcesTab === 'help' }" @click="resourcesTab = 'help'">
            Help
          </BaseButton>
          <BaseButton
            variant="tab"
            :class="{ 'cui-tab-active': resourcesTab === 'examples' }"
            @click="resourcesTab = 'examples'"
          >
            Examples
          </BaseButton>
        </div>

        <div v-if="resourcesTab === 'docs'" class="space-y-2 text-sm">
          <a
            class="flex items-center justify-between rounded border border-rth-border bg-rth-panel-muted p-3 text-rth-text transition-colors hover:border-rth-accent"
            href="/docs/"
            target="_blank"
            rel="noreferrer"
          >
            <span class="font-semibold">Project Docs</span>
            <span class="text-xs text-rth-muted">/docs/</span>
          </a>
          <a
            class="flex items-center justify-between rounded border border-rth-border bg-rth-panel-muted p-3 text-rth-text transition-colors hover:border-rth-accent"
            href="/API/ReticulumCommunityHub-OAS.yaml"
            target="_blank"
            rel="noreferrer"
          >
            <span class="font-semibold">OpenAPI Reference</span>
            <span class="text-xs text-rth-muted">/API/ReticulumCommunityHub-OAS.yaml</span>
          </a>
        </div>

        <div v-else-if="resourcesTab === 'help'">
          <BaseFormattedOutput v-if="helpContent" :value="helpContent" mode="markdown" />
          <div v-else class="text-xs text-rth-muted">Load help to view command references.</div>
          <div class="mt-4 flex flex-wrap justify-end gap-2">
            <BaseButton variant="secondary" icon-left="help" @click="loadHelp">Load Help</BaseButton>
          </div>
        </div>

        <div v-else>
          <BaseFormattedOutput v-if="examplesContent" :value="examplesContent" mode="markdown" />
          <div v-else class="text-xs text-rth-muted">Load examples to view command references.</div>
          <div class="mt-4 flex flex-wrap justify-end gap-2">
            <BaseButton variant="secondary" icon-left="list" @click="loadExamples">Load Examples</BaseButton>
          </div>
        </div>
      </BaseCard>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from "vue";
import { ref } from "vue";
import { storeToRefs } from "pinia";
import BaseButton from "../components/BaseButton.vue";
import BaseCard from "../components/BaseCard.vue";
import BaseFormattedOutput from "../components/BaseFormattedOutput.vue";
import { endpoints } from "../api/endpoints";
import { get } from "../api/client";
import { useAppStore } from "../stores/app";

const appStore = useAppStore();
const { appInfo } = storeToRefs(appStore);
const helpContent = ref<string | null>(null);
const examplesContent = ref<string | null>(null);
const resourcesTab = ref<"docs" | "help" | "examples">("docs");

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

const loadHelp = async () => {
  const response = await get<unknown>(endpoints.help);
  helpContent.value = typeof response === "string" ? response : JSON.stringify(response, null, 2);
};

const loadExamples = async () => {
  const response = await get<unknown>(endpoints.examples);
  examplesContent.value = typeof response === "string" ? response : JSON.stringify(response, null, 2);
};

onMounted(async () => {
  await appStore.fetchAppInfo();
});
</script>
