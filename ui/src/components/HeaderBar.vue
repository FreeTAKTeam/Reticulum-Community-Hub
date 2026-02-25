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
import { useConnectionPills } from "../composables/useConnectionPills";

const route = useRoute();

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

const { baseUrl, connectionLabel, wsLabel, connectionClass, wsClass } = useConnectionPills();
</script>
