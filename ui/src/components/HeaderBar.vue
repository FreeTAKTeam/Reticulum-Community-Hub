<template>
  <header class="flex items-center justify-between border-b border-rth-border bg-rth-panel-muted px-6 py-4">
    <div class="text-sm font-semibold uppercase tracking-[0.2em] text-rth-text">{{ title }}</div>
    <div class="flex items-center gap-3 text-xs text-rth-muted">
      <span class="rounded border border-rth-border bg-rth-panel px-2 py-1">{{ connectionLabel }}</span>
      <span class="rounded border border-rth-border bg-rth-panel px-2 py-1">{{ wsLabel }}</span>
      <span class="text-[11px]">{{ baseUrl }}</span>
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
const wsLabel = computed(() => connectionStore.wsLabel);
</script>
