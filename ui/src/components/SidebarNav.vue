<template>
  <aside
    class="cui-nav flex flex-col border-r border-rth-border bg-rth-panel text-rth-text transition-all duration-300 ease-out"
    :class="isCollapsed ? 'w-20 p-3' : 'w-64 p-4'"
  >
    <div class="flex text-sm text-rth-text" :class="isCollapsed ? 'mb-4 flex-col items-center gap-3' : 'mb-6 items-center gap-3'">
      <div class="flex items-center gap-3" :class="isCollapsed ? 'justify-center' : 'flex-1'">
        <div class="cui-logo-spin h-8 w-8">
          <img :src="logoUrl" alt="Reticulum Community Hub" class="h-full w-full" />
        </div>
        <div v-if="!isCollapsed" class="cui-title-wrap" :class="{ 'cui-title-paused': isTitlePaused }">
          <span class="cui-title-text" data-title="Reticulum Community Hub">Reticulum Community Hub</span>
        </div>
      </div>
      <div class="flex items-center gap-2" :class="isCollapsed ? 'flex-col' : ''">
        <button
          type="button"
          class="cui-btn cui-btn--ghost cui-btn--icon-only"
          :aria-label="isCollapsed ? 'Expand navigation' : 'Collapse navigation'"
          :title="isCollapsed ? 'Expand navigation' : 'Collapse navigation'"
          @click="navStore.toggleCollapsed"
        >
          <svg
            viewBox="0 0 24 24"
            class="h-4 w-4 transition-transform"
            :class="isCollapsed ? 'rotate-180' : ''"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
          >
            <path d="M15 18l-6-6 6-6" />
          </svg>
        </button>
        <button
          type="button"
          class="cui-btn cui-btn--ghost cui-btn--icon-only"
          :class="isPinned ? 'text-rth-text' : 'text-rth-muted'"
          :aria-label="isPinned ? 'Unpin navigation' : 'Pin navigation'"
          :aria-pressed="isPinned"
          :title="isPinned ? 'Unpin navigation' : 'Pin navigation'"
          @click="navStore.togglePinned"
        >
          <svg
            viewBox="0 0 24 24"
            class="h-4 w-4 transition-transform"
            :class="isPinned ? '' : 'rotate-45'"
            fill="none"
            stroke="currentColor"
            stroke-width="1.6"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
          >
            <path d="M9 3h6l1 5 3 3v2H5v-2l3-3z" />
            <path d="M12 14v7" />
          </svg>
        </button>
      </div>
    </div>
    <nav class="flex flex-1 flex-col gap-2 text-xs">
      <RouterLink
        v-for="item in navItems"
        :key="item.to"
        :to="item.to"
        :class="navItemClass(item.to)"
        :aria-label="item.label"
        :title="isCollapsed ? item.label : undefined"
        @click="navStore.collapseIfUnpinned"
      >
        <span class="flex h-6 w-6 items-center justify-center">
          <svg viewBox="0 0 24 24" class="h-4 w-4" :class="navIconClass(item.to)" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path v-for="(path, index) in navIcons[item.icon]" :key="index" :d="path" />
          </svg>
        </span>
        <span v-if="!isCollapsed" class="uppercase tracking-[0.2em]">{{ item.label }}</span>
      </RouterLink>
    </nav>
    <div class="mt-auto pt-6 text-[10px] uppercase tracking-[0.2em] text-rth-muted" :class="isCollapsed ? 'text-center' : ''">
      <div v-if="!isCollapsed">Build: {{ buildInfo }}</div>
      <div v-else :title="`Build: ${buildInfo}`">Build</div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { storeToRefs } from "pinia";
import { useRoute } from "vue-router";
import { RouterLink } from "vue-router";
import { useConnectionStore } from "../stores/connection";
import { useNavStore } from "../stores/nav";

const route = useRoute();
const connectionStore = useConnectionStore();
const navStore = useNavStore();
const { isCollapsed, isPinned } = storeToRefs(navStore);

const navItems = [
  { label: "Home", to: "/", icon: "home" },
  { label: "WebMap", to: "/webmap", icon: "map" },
  { label: "Topics", to: "/topics", icon: "topics" },
  { label: "Files", to: "/files", icon: "files" },
  { label: "Chat", to: "/chat", icon: "chat" },
  { label: "Users", to: "/users", icon: "users" },
  { label: "Configure", to: "/configure", icon: "config" },
  { label: "Connect", to: "/connect", icon: "connect" },
  { label: "About", to: "/about", icon: "about" }
];
const navIcons: Record<string, string[]> = {
  home: ["M4 10.5L12 4l8 6.5", "M6 20v-6h12v6"],
  map: ["M4 6l5-2 6 2 5-2v14l-5 2-6-2-5 2z", "M9 4v14", "M15 6v14"],
  topics: ["M12 12m-2 0a2 2 0 1 0 4 0a2 2 0 1 0-4 0", "M5 12a7 7 0 0 1 14 0", "M8 12a4 4 0 0 1 8 0"],
  files: ["M7 4h7l5 5v11a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1z", "M14 4v5h5"],
  chat: ["M21 15a4 4 0 0 1-4 4H7l-4 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z", "M8 9h8", "M8 13h5"],
  users: ["M12 12a3 3 0 1 0-3-3a3 3 0 0 0 3 3z", "M5 20a7 7 0 0 1 14 0"],
  config: ["M4 7h16", "M8 7m-2 0a2 2 0 1 0 4 0a2 2 0 1 0-4 0", "M4 17h16", "M14 17m-2 0a2 2 0 1 0 4 0a2 2 0 1 0-4 0"],
  about: ["M12 4a8 8 0 1 0 0.01 0", "M12 10v6", "M12 8h.01"],
  connect: ["M10 13a3 3 0 0 1 0-4l2-2a3 3 0 0 1 4 4l-1 1", "M14 11a3 3 0 0 1 0 4l-2 2a3 3 0 0 1-4-4l1-1"]
};

const navItemClass = (path: string) => {
  const base = "flex items-center rounded py-2 transition-colors hover:bg-rth-border";
  const layout = isCollapsed.value ? "justify-center px-2" : "gap-3 px-3";
  const state =
    route.path === path
      ? "bg-rth-panel-muted text-rth-text border-l-2 border-rth-accent"
      : "text-rth-muted border-l-2 border-transparent";
  return `${base} ${layout} ${state}`;
};

const navIconClass = (path: string) => {
  return route.path === path ? "text-rth-accent" : "text-rth-muted";
};

const buildInfo = computed(() => {
  return import.meta.env.VITE_BUILD_ID ?? "local";
});

const isTitlePaused = computed(() => {
  return (
    connectionStore.status === "offline" ||
    connectionStore.authStatus === "unauthenticated" ||
    connectionStore.authStatus === "forbidden"
  );
});

const logoUrl = `${import.meta.env.BASE_URL}RCH_vector.svg`;
</script>
