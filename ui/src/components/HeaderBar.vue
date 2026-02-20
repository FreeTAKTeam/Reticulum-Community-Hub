<template>
  <header v-if="showHeader" class="cui-page-header">
    <div class="cui-page-header__grid">
      <div class="cui-page-header__title">{{ title }}</div>
      <div class="cui-page-header__status">
        <OnlineHelpLauncher />
        <span class="cui-status-pill" :class="connectionClass">{{ connectionLabel }}</span>
        <span class="cui-status-pill" :class="wsClass">{{ wsLabel }}</span>
        <span class="cui-page-header__url">{{ baseUrl }}</span>
      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";
import OnlineHelpLauncher from "./OnlineHelpLauncher.vue";
import { useConnectionStore } from "../stores/connection";

const route = useRoute();
const connectionStore = useConnectionStore();

const title = computed(() => {
  const mapping: Record<string, string> = {
    "/": "Dashboard",
    "/missions": "Missions",
    "/webmap": "WebMap",
    "/topics": "Topics",
    "/files": "Files",
    "/chat": "Communications",
    "/users": "Users",
    "/configure": "Configure",
    "/about": "About",
    "/connect": "Connect"
  };
  return mapping[route.path] ?? "RCH";
});

const showHeader = computed(() => route.path !== "/topics");

const baseUrl = computed(() => connectionStore.baseUrlDisplay);
const connectionLabel = computed(() => connectionStore.statusLabel);
const wsLabel = computed(() => connectionStore.wsLabel);

const connectionClass = computed(() => {
  if (connectionStore.status === "online") {
    return "cui-status-success";
  }
  if (connectionStore.status === "offline") {
    return "cui-status-danger";
  }
  return "cui-status-accent";
});

const wsClass = computed(() => {
  if (connectionStore.wsLabel.toLowerCase() === "live") {
    return "cui-status-success";
  }
  return "cui-status-accent";
});
</script>
