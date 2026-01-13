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
    return "bg-[#4db6ff]/15 text-[#8fd4ff]";
  }
  if (props.tone === "warning") {
    return "bg-[#f59e0b]/15 text-[#fcd34d]";
  }
  if (props.tone === "danger") {
    return "bg-[#ef4444]/15 text-[#fecaca]";
  }
  return "bg-rth-panel-muted text-rth-muted";
});
</script>
