<template>
  <div class="rounded border border-rth-border bg-rth-panel p-4 shadow-sm">
    <div v-if="title" class="mb-2 text-sm font-semibold text-slate-100">{{ title }}</div>
    <slot />
  </div>
</template>

<script setup lang="ts">
defineProps<{ title?: string }>();
</script>
