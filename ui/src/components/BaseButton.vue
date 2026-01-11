<template>
  <button :type="type" class="inline-flex items-center justify-center gap-2 rounded border border-rth-border bg-rth-border px-3 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50" :class="variantClass">
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
    return "bg-transparent border-transparent hover:bg-rth-border";
  }
  if (props.variant === "secondary") {
    return "bg-slate-800";
  }
  return "bg-rth-accent text-slate-900 hover:bg-sky-300";
});
</script>
