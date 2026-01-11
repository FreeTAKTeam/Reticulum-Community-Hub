<template>
  <div v-if="showBanner" class="border-b border-rth-border bg-amber-500/10 px-6 py-2 text-sm text-amber-200">
    <span class="font-semibold">Connection issue:</span> {{ message }}
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useConnectionStore } from "../stores/connection";

const connectionStore = useConnectionStore();

const showBanner = computed(() => connectionStore.status === "offline");
const message = computed(() => connectionStore.statusMessage || "Unable to reach the hub. Retrying..." );
</script>
