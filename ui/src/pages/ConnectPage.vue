<template>
  <div class="space-y-6">
    <BaseCard :title="connectionStore.isRemoteTarget ? 'Remote Login' : 'Connection Settings'">
      <div class="grid gap-4 md:grid-cols-2">
        <BaseInput v-model="connectionStore.baseUrl" label="Base URL" />
        <BaseInput v-model="connectionStore.wsBaseUrl" label="WebSocket Base URL" />

        <template v-if="connectionStore.isRemoteTarget">
          <BaseSelect v-model="connectionStore.authMode" label="Auth Mode" :options="authOptions" />
          <BaseInput v-model="connectionStore.token" label="Bearer Token" type="password" />
          <BaseInput v-model="connectionStore.apiKey" label="API Key" type="password" />
          <div class="md:col-span-2">
            <BaseCheckbox v-model="connectionStore.rememberSecrets" label="Remember credentials on this device" />
          </div>
        </template>
      </div>

      <div v-if="testResult" class="mt-3 text-sm text-rth-muted">{{ testResult }}</div>
      <div class="mt-4 flex justify-end gap-2">
        <BaseButton icon-left="save" @click="save">Save</BaseButton>
        <BaseButton
          v-if="connectionStore.isRemoteTarget"
          icon-left="account-key"
          :disabled="isSubmitting"
          @click="login"
        >
          Log in
        </BaseButton>
        <BaseButton v-else variant="secondary" icon-left="link" :disabled="isSubmitting" @click="testConnection">
          Test Connection
        </BaseButton>
      </div>
    </BaseCard>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import BaseButton from "../components/BaseButton.vue";
import BaseCard from "../components/BaseCard.vue";
import BaseCheckbox from "../components/BaseCheckbox.vue";
import BaseInput from "../components/BaseInput.vue";
import BaseSelect from "../components/BaseSelect.vue";
import { endpoints } from "../api/endpoints";
import { get } from "../api/client";
import type { ApiError } from "../api/client";
import { useConnectionStore } from "../stores/connection";
import { useToastStore } from "../stores/toasts";

const connectionStore = useConnectionStore();
const toastStore = useToastStore();
const router = useRouter();
const testResult = ref("");
const isSubmitting = ref(false);

const authOptions = [
  { label: "Bearer", value: "bearer" },
  { label: "API Key", value: "apiKey" },
  { label: "Both", value: "both" }
];

const save = () => {
  connectionStore.persist(connectionStore.rememberSecrets);
  toastStore.push("Connection settings saved", "success");
};

const login = async () => {
  isSubmitting.value = true;
  testResult.value = "";
  connectionStore.persist(connectionStore.rememberSecrets);
  try {
    const status = await get(endpoints.status);
    connectionStore.markAuthenticated();
    testResult.value = `Authenticated: ${JSON.stringify(status)}`;
    toastStore.push("Login successful", "success");
    const redirect = typeof router.currentRoute.value.query.redirect === "string" ? router.currentRoute.value.query.redirect : "/";
    await router.push(redirect);
  } catch (error) {
    connectionStore.setAuthStatus("unauthenticated", "Login failed. Check credentials.");
    const apiError = error as ApiError;
    testResult.value = `Login failed${apiError?.status ? ` (${apiError.status})` : ""}`;
    toastStore.push("Login failed", "error");
  } finally {
    isSubmitting.value = false;
  }
};

const testConnection = async () => {
  isSubmitting.value = true;
  testResult.value = "";
  try {
    const appInfo = await get(endpoints.appInfo);
    const status = await get(endpoints.status);
    testResult.value = `Connected: ${JSON.stringify(appInfo)} / ${JSON.stringify(status)}`;
    toastStore.push("Connection successful", "success");
    connectionStore.setOnline();
    connectionStore.markAuthenticated();
  } finally {
    isSubmitting.value = false;
  }
};
</script>
