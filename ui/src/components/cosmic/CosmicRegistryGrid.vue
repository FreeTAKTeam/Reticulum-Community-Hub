<template>
  <div class="registry-grid" :class="{ 'registry-grid-full': fullWidth }">
    <slot />
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    fullWidth?: boolean;
  }>(),
  {
    fullWidth: false
  }
);
</script>
