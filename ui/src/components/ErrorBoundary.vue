<template>
  <div v-if="error" class="space-y-4 rounded border border-rth-border bg-rth-panel p-6 text-rth-text">
    <div class="text-lg font-semibold">Something went wrong</div>
    <div class="text-sm text-rth-muted">{{ error.message }}</div>
    <BaseButton variant="secondary" @click="reload">Reload</BaseButton>
  </div>
  <slot v-else />
</template>

<script setup lang="ts">
import { onErrorCaptured, ref } from "vue";
import BaseButton from "./BaseButton.vue";

const error = ref<Error | null>(null);

const reload = () => {
  window.location.reload();
};

onErrorCaptured((err) => {
  error.value = err as Error;
  return false;
});
</script>
