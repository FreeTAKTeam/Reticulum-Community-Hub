<template>
  <aside class="flex w-64 flex-col border-r border-rth-border bg-rth-panel p-4">
    <div class="mb-6 text-lg font-semibold">RTH Core UI</div>
    <nav class="flex flex-col gap-2 text-sm">
      <RouterLink v-for="item in navItems" :key="item.to" :to="item.to" class="rounded px-3 py-2 hover:bg-rth-border" :class="route.path === item.to ? 'bg-rth-border text-white' : 'text-slate-300'">
        {{ item.label }}
      </RouterLink>
    </nav>
    <div class="mt-auto pt-6 text-xs text-slate-400">
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
  { label: "Home", to: "/" },
  { label: "WebMap", to: "/webmap" },
  { label: "Topics", to: "/topics" },
  { label: "Files", to: "/files" },
  { label: "Users", to: "/users" },
  { label: "Configure", to: "/configure" },
  { label: "About", to: "/about" },
  { label: "Connect", to: "/connect" }
];

const buildInfo = computed(() => {
  return import.meta.env.VITE_BUILD_ID ?? "local";
});
</script>
