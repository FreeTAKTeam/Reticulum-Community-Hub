<template>
  <button :type="type" class="inline-flex items-center justify-center gap-2 rounded border border-rth-border px-3 py-2 text-sm font-semibold text-rth-text transition-colors hover:border-rth-accent disabled:cursor-not-allowed disabled:opacity-50" :class="variantClass">
    <slot />
  </button>
</template>

<script setup lang="ts">
import { computed } from "vue";

const props = withDefaults(defineProps<{ variant?: "primary" | "secondary" | "ghost"; type?: "button" | "submit" | "reset" }>(), {
  variant: "primary",
  type: "button"
});

const variantClass = computed(() => {
  if (props.variant === "ghost") {
    return "bg-transparent border-transparent text-rth-muted hover:bg-rth-border";
  }
  if (props.variant === "secondary") {
    return "bg-rth-panel-muted text-rth-text hover:bg-rth-border";
  }
  return "bg-rth-accent text-rth-bg hover:bg-[#67c5ff]";
});
</script>
