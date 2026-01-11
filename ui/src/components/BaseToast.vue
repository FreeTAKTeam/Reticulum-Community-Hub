<template>
  <div class="fixed bottom-6 right-6 z-50 flex flex-col gap-2">
    <div v-for="toast in toastStore.messages" :key="toast.id" class="rounded border border-rth-border bg-slate-900 px-4 py-2 text-sm shadow" :class="toneClass(toast.tone)">
      {{ toast.message }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { useToastStore } from "../stores/toasts";

const toastStore = useToastStore();

const toneClass = (tone: string) => {
  if (tone === "success") {
    return "text-emerald-200";
  }
  if (tone === "error") {
    return "text-rose-200";
  }
  if (tone === "warning") {
    return "text-amber-200";
  }
  return "text-slate-200";
};
</script>
