<template>
  <div v-if="open" class="fixed inset-0 z-50 flex justify-end bg-black/60">
    <div class="h-full w-full max-w-md border-l border-rth-border bg-rth-panel p-6 shadow-lg">
      <div class="flex items-start justify-between">
        <h3 class="text-lg font-semibold">{{ title }}</h3>
        <button class="text-slate-400 hover:text-white" @click="emit('close')">✕</button>
      </div>
      <div class="mt-4">
        <slot />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const props = defineProps<{ open: boolean; title: string }>();
const emit = defineEmits<{ (event: "close"): void }>();
</script>
