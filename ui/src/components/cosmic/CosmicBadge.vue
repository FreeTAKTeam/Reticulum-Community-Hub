<template>
  <BaseBadge :tone="tone"><slot /></BaseBadge>
</template>

<script setup lang="ts">
import BaseBadge from "../BaseBadge.vue";

import type { CosmicTone } from "../../types/cosmic-ui";

withDefaults(
  defineProps<{
    tone?: CosmicTone;
  }>(),
  {
    tone: "neutral"
  }
);
</script>
