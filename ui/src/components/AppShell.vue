<template>
  <div class="flex min-h-screen bg-rth-bg text-rth-text">
    <SidebarNav />
    <div class="flex flex-1 flex-col">
      <HeaderBar />
      <ConnectionBanner />
      <main class="flex-1 overflow-y-auto p-6">
        <slot />
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import ConnectionBanner from "./ConnectionBanner.vue";
import HeaderBar from "./HeaderBar.vue";
import SidebarNav from "./SidebarNav.vue";
</script>
