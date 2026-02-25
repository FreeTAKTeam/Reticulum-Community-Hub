<template>
  <section class="panel" :class="panelClass">
    <slot />
  </section>
</template>

<script setup lang="ts">
import { computed } from "vue";

const props = withDefaults(
  defineProps<{
    compact?: boolean;
  }>(),
  {
    compact: false
  }
);

const panelClass = computed(() => (props.compact ? "p-3" : ""));
</script>
