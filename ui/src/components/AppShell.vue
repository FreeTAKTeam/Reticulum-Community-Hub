<template>
  <div class="flex bg-rth-bg text-rth-text" :class="shellClass">
    <SidebarNav />
    <div class="flex flex-1 min-w-0 flex-col min-h-0">
      <HeaderBar v-if="showHeaderBar" />
      <ConnectionBanner />
      <main class="flex-1 min-h-0" :class="mainClass">
        <slot />
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";
import ConnectionBanner from "./ConnectionBanner.vue";
import HeaderBar from "./HeaderBar.vue";
import SidebarNav from "./SidebarNav.vue";

const route = useRoute();
const showHeaderBar = computed(
  () =>
    route.path !== "/" &&
    route.path !== "/users" &&
    route.path !== "/missions" &&
    route.path !== "/checklists" &&
    route.path !== "/files"
);
const isViewportLockedRoute = computed(() => route.path === "/" || route.path === "/chat");
const shellClass = computed(() =>
  isViewportLockedRoute.value ? "h-screen overflow-hidden" : "min-h-screen"
);
const mainClass = computed(() => {
  if (route.path === "/") {
    return "p-2 overflow-hidden flex flex-col min-h-0";
  }
  if (route.path === "/chat") {
    return "p-4 overflow-hidden flex flex-col min-h-0";
  }
  return "p-6 overflow-y-auto";
});
</script>
