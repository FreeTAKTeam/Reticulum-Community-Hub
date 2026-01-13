<template>
  <div class="fixed bottom-6 right-6 z-50 flex flex-col gap-2">
    <div v-for="toast in toastStore.messages" :key="toast.id" class="rounded border border-rth-border bg-rth-panel-muted px-4 py-2 text-sm" :class="toneClass(toast.tone)">
      {{ toast.message }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { useToastStore } from "../stores/toasts";

const toastStore = useToastStore();

const toneClass = (tone: string) => {
  if (tone === "success") {
    return "text-[#8fd4ff]";
  }
  if (tone === "error" || tone === "danger") {
    return "text-[#fecaca]";
  }
  if (tone === "warning") {
    return "text-[#fcd34d]";
  }
  return "text-rth-text";
};
</script>
