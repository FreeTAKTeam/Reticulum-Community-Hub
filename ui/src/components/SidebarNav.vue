<template>
  <aside class="flex w-64 flex-col border-r border-rth-border bg-rth-panel p-4 text-rth-text">
    <div class="mb-6 flex items-center gap-2 text-xs text-rth-text">
      <img src="/RCH_small.png" alt="Reticulum Community Hub" class="h-5 w-5" />
      <span class="uppercase tracking-[0.2em]">R C H</span>
    </div>
    <nav class="flex flex-col gap-2 text-xs">
      <RouterLink
        v-for="item in navItems"
        :key="item.to"
        :to="item.to"
        class="flex items-center gap-3 rounded px-3 py-2 transition-colors hover:bg-rth-border"
        :class="route.path === item.to ? 'bg-rth-panel-muted text-rth-text border-l-2 border-rth-accent' : 'text-rth-muted border-l-2 border-transparent'"
      >
        <span class="flex h-6 w-6 items-center justify-center">
          <svg viewBox="0 0 24 24" class="h-4 w-4" :class="route.path === item.to ? 'text-rth-accent' : 'text-rth-muted'" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path v-for="(path, index) in navIcons[item.icon]" :key="index" :d="path" />
          </svg>
        </span>
        <span class="uppercase tracking-[0.2em]">{{ item.label }}</span>
      </RouterLink>
    </nav>
    <div class="mt-auto pt-6 text-[10px] uppercase tracking-[0.2em] text-rth-muted">
      <div>Build: {{ buildInfo }}</div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";
import { RouterLink } from "vue-router";

const route = useRoute();

const navItems = [
  { label: "Home", to: "/", icon: "home" },
  { label: "WebMap", to: "/webmap", icon: "map" },
  { label: "Topics", to: "/topics", icon: "topics" },
  { label: "Files", to: "/files", icon: "files" },
  { label: "Users", to: "/users", icon: "users" },
  { label: "Configure", to: "/configure", icon: "config" },
  { label: "About", to: "/about", icon: "about" },
  { label: "Connect", to: "/connect", icon: "connect" }
];

const navIcons: Record<string, string[]> = {
  home: ["M4 10.5L12 4l8 6.5", "M6 20v-6h12v6"],
  map: ["M4 6l5-2 6 2 5-2v14l-5 2-6-2-5 2z", "M9 4v14", "M15 6v14"],
  topics: ["M12 12m-2 0a2 2 0 1 0 4 0a2 2 0 1 0-4 0", "M5 12a7 7 0 0 1 14 0", "M8 12a4 4 0 0 1 8 0"],
  files: ["M7 4h7l5 5v11a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1z", "M14 4v5h5"],
  users: ["M12 12a3 3 0 1 0-3-3a3 3 0 0 0 3 3z", "M5 20a7 7 0 0 1 14 0"],
  config: ["M4 7h16", "M8 7m-2 0a2 2 0 1 0 4 0a2 2 0 1 0-4 0", "M4 17h16", "M14 17m-2 0a2 2 0 1 0 4 0a2 2 0 1 0-4 0"],
  about: ["M12 4a8 8 0 1 0 0.01 0", "M12 10v6", "M12 8h.01"],
  connect: ["M10 13a3 3 0 0 1 0-4l2-2a3 3 0 0 1 4 4l-1 1", "M14 11a3 3 0 0 1 0 4l-2 2a3 3 0 0 1-4-4l1-1"]
};

const buildInfo = computed(() => {
  return import.meta.env.VITE_BUILD_ID ?? "local";
});
</script>
