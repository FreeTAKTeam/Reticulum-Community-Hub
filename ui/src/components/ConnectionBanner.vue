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
const showAuth = computed(
  () => connectionStore.authStatus === "unauthenticated" || connectionStore.authStatus === "forbidden"
);
const showBanner = computed(() => showOffline.value || showAuth.value);

const bannerClass = computed(() => {
  if (showAuth.value) {
    return "bg-[#ef4444]/15 text-[#fecaca]";
  }
  return "bg-[#f59e0b]/15 text-[#fcd34d]";
});

const label = computed(() => (showAuth.value ? "Auth issue:" : "Connection issue:"));
const message = computed(() => {
  if (showAuth.value) {
    return connectionStore.authMessage || connectionStore.authLabel || "Check credentials and permissions.";
  }
  return connectionStore.statusMessage || "Unable to reach the hub. Retrying...";
});
</script>
