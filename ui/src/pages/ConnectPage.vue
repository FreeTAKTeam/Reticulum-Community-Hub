<template>
  <div class="space-y-6">
    <BaseCard :title="connectionStore.isRemoteTarget ? 'Remote Connection' : 'Local Connection Settings'">
      <div class="grid gap-4 md:grid-cols-2">
        <BaseInput id="connect-base-url" v-model="connectionStore.baseUrl" label="Base URL" />
        <BaseInput id="connect-ws-url" v-model="connectionStore.wsBaseUrl" label="WebSocket Base URL" />

          <div class="md:col-span-2 rounded-md border border-rth-warning/40 bg-rth-warning/10 px-3 py-2 text-sm text-rth-warning">
            Use the enrolled remote access password as an API key, or enter the configured API key or bearer token. Remote connections require HTTPS and WSS.
          </div>
          <BaseSelect v-model="connectionStore.authMode" label="Auth Mode" :options="authOptions" />
          <BaseInput id="connect-token" v-model="connectionStore.token" label="Bearer Token" type="password" />
          <BaseInput id="connect-api-key" v-model="connectionStore.apiKey" label="API Key" type="password" />
          <div class="md:col-span-2">
            <BaseCheckbox v-model="connectionStore.rememberSecrets" label="Remember credentials on this device" />
          </div>
          <div v-if="connectionStore.authValidationError" class="md:col-span-2 text-sm text-rth-danger">
            {{ connectionStore.authValidationError }}
          </div>


      </div>

      <div v-if="testResult" class="mt-3 text-sm text-rth-muted">{{ testResult }}</div>
      <div class="mt-4 flex justify-end gap-2">
        <BaseButton icon-left="save" @click="save">Save</BaseButton>
        <BaseButton
          icon-left="account-key"
          :disabled="isSubmitting"
          @click="login"
        >
          Log in
        </BaseButton>

      </div>
    </BaseCard>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from "vue";
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
if (connectionStore.authMode === "none") { connectionStore.authMode = "apiKey"; }
const toastStore = useToastStore();
const router = useRouter();
const testResult = ref("");
const isSubmitting = ref(false);
let pendingLogin: AbortController | undefined;
let disposed = false;
watch(() => connectionStore.requestIdentity, () => pendingLogin?.abort(), { flush: "sync" });
onBeforeUnmount(() => { disposed = true; pendingLogin?.abort(); });

const authOptions = [
  { label: "None (local only)", value: "none" },
  { label: "Bearer", value: "bearer" },
  { label: "API Key", value: "apiKey" },
  { label: "Both", value: "both" }
];

const save = () => {
  if (!connectionStore.hasValidAuthConfig()) {
    toastStore.push(connectionStore.authValidationError, "error");
    return;
  }
  connectionStore.persist(connectionStore.rememberSecrets);
  toastStore.push("Connection settings saved", "success");
};

const login = async () => {
  isSubmitting.value = true;
  testResult.value = "";
  if (!connectionStore.hasValidAuthConfig()) {
    connectionStore.setAuthStatus("unauthenticated", connectionStore.authValidationError);
    testResult.value = connectionStore.authValidationError;
    toastStore.push(connectionStore.authValidationError, "error");
    isSubmitting.value = false;
    return;
  }
  connectionStore.persist(connectionStore.rememberSecrets);
  const identity = connectionStore.requestIdentity;
  const controller = new AbortController();
  pendingLogin = controller;
  try {
    const status = await get(endpoints.status, { signal: controller.signal, retries: 0 });
    if (disposed || controller.signal.aborted) { return; }
    if (!connectionStore.markAuthenticated(identity)) {
      testResult.value = "Connection settings changed. Log in again.";
      return;
    }
    testResult.value = `Authenticated: ${JSON.stringify(status)}`;
    toastStore.push("Login successful", "success");
    const redirect = typeof router.currentRoute.value.query.redirect === "string" ? router.currentRoute.value.query.redirect : "/";
    await router.push(redirect);
  } catch (error) {
    if (disposed || controller.signal.aborted || identity !== connectionStore.requestIdentity) { return; }
    connectionStore.setAuthStatus("unauthenticated", "Login failed. Check credentials.");
    const apiError = error as ApiError;
    testResult.value = `Login failed${apiError?.status ? ` (${apiError.status})` : ""}`;
    toastStore.push("Login failed", "error");
  } finally {
    if (pendingLogin === controller) { pendingLogin = undefined; }
    isSubmitting.value = false;
  }
};

</script>
