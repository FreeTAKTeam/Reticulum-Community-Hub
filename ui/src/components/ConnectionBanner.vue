<template>
  <div v-if="showBanner" class="border-b border-rth-border px-6 py-2 text-sm" :class="bannerClass">
    <span class="font-semibold">{{ label }}</span> {{ message }}
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useConnectionStore } from "../stores/connection";

const connectionStore = useConnectionStore();

const showOffline = computed(() => connectionStore.status === "offline");
const showLoginRequired = computed(() => connectionStore.requiresLogin);
const showForbidden = computed(() => connectionStore.authStatus === "forbidden");
const showBanner = computed(() => showOffline.value || showLoginRequired.value || showForbidden.value);

const bannerClass = computed(() => {
  if (showLoginRequired.value || showForbidden.value) {
    return "bg-[#ef4444]/15 text-[#fecaca]";
  }
  return "bg-[#f59e0b]/15 text-[#fcd34d]";
});

const label = computed(() => {
  if (showLoginRequired.value) {
    return "Login required:";
  }
  if (showForbidden.value) {
    return "Auth issue:";
  }
  return "Connection offline:";
});

const message = computed(() => {
  if (showLoginRequired.value) {
    return connectionStore.authMessage || "Authenticate on the Connect page to access this remote hub.";
  }
  if (showForbidden.value) {
    return connectionStore.authMessage || "Your credentials are valid but do not have permission.";
  }
  return connectionStore.statusMessage || "Unable to reach the hub. Retrying...";
});
</script>
