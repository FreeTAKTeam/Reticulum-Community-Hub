<template>
  <BaseModal :open="open" :title="title" :size="size" :hide-close="hideClose" @close="emit('close')">
    <template v-if="$slots.header" #header>
      <slot name="header" />
    </template>
    <slot />
    <template v-if="$slots.footer" #footer>
      <slot name="footer" />
    </template>
  </BaseModal>
</template>

<script setup lang="ts">
import BaseModal from "../BaseModal.vue";

import type { CosmicSize } from "../../types/cosmic-ui";

withDefaults(
  defineProps<{
    open: boolean;
    title?: string;
    size?: CosmicSize;
    hideClose?: boolean;
  }>(),
  {
    title: "",
    size: "md",
    hideClose: false
  }
);

const emit = defineEmits<{ (event: "close"): void }>();
</script>
