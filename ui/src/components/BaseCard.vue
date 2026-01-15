<template>
  <div class="cui-panel p-4">
    <div v-if="title" class="mb-2 text-sm font-semibold text-rth-text">{{ title }}</div>
    <slot />
  </div>
</template>

<script setup lang="ts">
defineProps<{ title?: string }>();
</script>
