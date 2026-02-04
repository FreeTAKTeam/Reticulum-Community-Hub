<template>
  <BootScreen
    v-if="!bootReady"
    :status="bootStatus"
    :status-text="bootStatusText"
    :detail="bootDetail"
    :progress="bootProgress"
    :logs="bootLogs"
  />
  <AppShell v-else>
    <ErrorBoundary>
      <RouterView />
    </ErrorBoundary>
  </AppShell>
  <BaseToast />
</template>

<script setup lang="ts">
import { computed } from "vue";
import { onMounted } from "vue";
import { ref } from "vue";
import { RouterView } from "vue-router";
import AppShell from "./components/AppShell.vue";
import BaseToast from "./components/BaseToast.vue";
import BootScreen from "./components/BootScreen.vue";
import ErrorBoundary from "./components/ErrorBoundary.vue";
import { endpoints } from "./api/endpoints";
import { useAppStore } from "./stores/app";
import { useConnectionStore } from "./stores/connection";

type BootStatus = "pending" | "retrying" | "online";

const appStore = useAppStore();
const connectionStore = useConnectionStore();
const bootReady = ref(false);
const bootStatus = ref<BootStatus>("pending");
const bootAttempt = ref(0);
const bootProgress = ref(12);
const bootError = ref("");

const POLL_INTERVAL_MS = 2000;
const MIN_DISPLAY_MS = 1000;
const MAX_PROGRESS = 92;

const bootStatusText = computed(() => {
  if (bootStatus.value === "online") {
    return "online";
  }
  if (bootStatus.value === "retrying") {
    return `retry ${bootAttempt.value}`;
  }
  return "pending";
});

const bootDetail = computed(() => {
  const wsUrl = connectionStore.resolveWsUrl("/events/system");
  return `WS ${wsUrl}`;
});

const bootLogs = computed(() => {
  const statusToken = bootStatus.value === "online" ? "ok" : "pending";
  const lines = [
    "handshake protocol initialized... ok",
    `websocket bridge handshake... ${statusToken}`,
    `retrieving hub metadata... ${statusToken}`,
    `target ${connectionStore.resolveUrl(endpoints.appInfo)}`
  ];
  if (bootStatus.value === "retrying") {
    const retrySeconds = Math.ceil(POLL_INTERVAL_MS / 1000);
    const errorSuffix = bootError.value ? ` (${bootError.value})` : "";
    lines.push(`retrying in ${retrySeconds}s${errorSuffix}`);
  }
  return lines;
});

const delay = (ms: number) =>
  new Promise<void>((resolve) => {
    window.setTimeout(resolve, ms);
  });

const advanceProgress = () => {
  const increment = 5 + Math.random() * 7;
  bootProgress.value = Math.min(MAX_PROGRESS, bootProgress.value + increment);
};

const waitForBackend = async () => {
  const start = Date.now();
  if (import.meta.env.VITE_RTH_MOCK === "true") {
    await delay(800);
    bootProgress.value = 100;
    bootStatus.value = "online";
    bootReady.value = true;
    return;
  }
  while (!bootReady.value) {
    bootAttempt.value += 1;
    bootStatus.value = bootAttempt.value > 1 ? "retrying" : "pending";
    try {
      await appStore.fetchAppInfo(true);
      bootStatus.value = "online";
      bootProgress.value = 100;
      const elapsed = Date.now() - start;
      if (elapsed < MIN_DISPLAY_MS) {
        await delay(MIN_DISPLAY_MS - elapsed);
      }
      bootReady.value = true;
      return;
    } catch (error) {
      bootError.value = error instanceof Error ? error.message : "unreachable";
      advanceProgress();
      await delay(POLL_INTERVAL_MS);
    }
  }
};

onMounted(() => {
  void waitForBackend();
});
</script>
