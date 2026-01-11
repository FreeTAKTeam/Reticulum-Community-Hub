<template>
  <header class="flex items-center justify-between border-b border-rth-border bg-rth-panel px-6 py-4">
    <div class="text-lg font-semibold">{{ title }}</div>
    <div class="flex items-center gap-3 text-xs text-slate-300">
      <span class="rounded bg-rth-border px-2 py-1">{{ connectionLabel }}</span>
      <span>{{ baseUrl }}</span>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";
import { useConnectionStore } from "../stores/connection";

const route = useRoute();
const connectionStore = useConnectionStore();

const title = computed(() => {
  const mapping: Record<string, string> = {
    "/": "Dashboard",
    "/webmap": "WebMap",
    "/topics": "Topics",
    "/files": "Files",
    "/users": "Users",
    "/configure": "Configure",
    "/about": "About",
    "/connect": "Connect"
  };
  return mapping[route.path] ?? "RTH Core UI";
});

const baseUrl = computed(() => connectionStore.baseUrlDisplay);
const connectionLabel = computed(() => connectionStore.statusLabel);
</script>
