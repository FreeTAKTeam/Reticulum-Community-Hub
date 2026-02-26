<template>
  <div class="space-y-6">
    <BaseCard title="Connection Settings">
      <div class="grid gap-4 md:grid-cols-2">
        <BaseInput v-model="connectionStore.baseUrl" label="Base URL" />
        <BaseInput v-model="connectionStore.wsBaseUrl" label="WebSocket Base URL" />
        <BaseSelect v-model="connectionStore.authMode" label="Auth Mode" :options="authOptions" />
        <BaseInput v-model="connectionStore.token" label="Bearer Token" />
        <BaseInput v-model="connectionStore.apiKey" label="API Key" />
      </div>
      <div v-if="testResult" class="mt-3 text-sm text-rth-muted">{{ testResult }}</div>
      <div class="mt-4 flex justify-end gap-2">
        <BaseButton icon-left="save" @click="save">Save</BaseButton>
        <BaseButton variant="secondary" icon-left="link" @click="testConnection">Test Connection</BaseButton>
      </div>
    </BaseCard>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import BaseButton from "../components/BaseButton.vue";
import BaseCard from "../components/BaseCard.vue";
import BaseInput from "../components/BaseInput.vue";
import BaseSelect from "../components/BaseSelect.vue";
import { endpoints } from "../api/endpoints";
import { get } from "../api/client";
import { useConnectionStore } from "../stores/connection";
import { useToastStore } from "../stores/toasts";

const connectionStore = useConnectionStore();
const toastStore = useToastStore();
const testResult = ref("");

const authOptions = [
  { label: "None", value: "none" },
  { label: "Bearer", value: "bearer" },
  { label: "API Key", value: "apiKey" },
  { label: "Both", value: "both" }
];

const save = () => {
  connectionStore.persist();
  toastStore.push("Connection settings saved", "success");
};

const testConnection = async () => {
  const appInfo = await get(endpoints.appInfo);
  const status = await get(endpoints.status);
  testResult.value = `Connected: ${JSON.stringify(appInfo)} / ${JSON.stringify(status)}`;
  toastStore.push("Connection successful", "success");
  connectionStore.setOnline();
};
</script>

