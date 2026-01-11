<template>
  <span class="rounded border border-rth-border px-2 py-1 text-xs font-semibold" :class="badgeClass">
    <slot />
  </span>
</template>

<script setup lang="ts">
import { computed } from "vue";

const props = withDefaults(defineProps<{ tone?: "neutral" | "success" | "warning" | "danger" }>(), {
  tone: "neutral"
});

const badgeClass = computed(() => {
  if (props.tone === "success") {
    return "bg-emerald-500/20 text-emerald-200";
  }
  if (props.tone === "warning") {
    return "bg-amber-500/20 text-amber-200";
  }
  if (props.tone === "danger") {
    return "bg-rose-500/20 text-rose-200";
  }
  return "bg-slate-800 text-slate-200";
});
</script>
