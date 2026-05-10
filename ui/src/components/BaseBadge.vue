<template>
  <span class="cui-badge" :class="badgeClass">
    <slot />
  </span>
</template>

<script setup lang="ts">
import { computed } from "vue";

import type { CosmicTone } from "../types/cosmic-ui";

const props = withDefaults(defineProps<{ tone?: CosmicTone }>(), {
  tone: "neutral"
});

const badgeClass = computed(() => {
  if (props.tone === "success") {
    return "cui-badge--success";
  }
  if (props.tone === "warning") {
    return "cui-badge--warning";
  }
  if (props.tone === "danger") {
    return "cui-badge--danger";
  }
  if (props.tone === "info" || props.tone === "primary" || props.tone === "secondary") {
    return "cui-badge--info";
  }
  return "cui-badge--neutral";
});
</script>
