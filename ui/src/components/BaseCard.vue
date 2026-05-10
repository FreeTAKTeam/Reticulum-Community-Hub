<template>
  <article class="cui-panel p-4" :class="cardClass">
    <header v-if="title || $slots.header" class="mb-2 flex items-start justify-between gap-3">
      <slot name="header">
        <div class="text-sm font-semibold text-rth-text">{{ title }}</div>
      </slot>
    </header>
    <slot />
  </article>
</template>

<script setup lang="ts">
import { computed } from "vue";

const props = withDefaults(
  defineProps<{
    title?: string;
    compact?: boolean;
  }>(),
  {
    title: "",
    compact: false
  }
);

const cardClass = computed(() => (props.compact ? "p-3" : "p-4"));
</script>
