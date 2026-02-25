<template>
  <span class="cui-chip" :class="chipClass"><slot /></span>
</template>

<script setup lang="ts">
import { computed } from "vue";

const props = withDefaults(
  defineProps<{
    tone?: "neutral" | "success" | "warning" | "danger";
  }>(),
  {
    tone: "neutral"
  }
);

const chipClass = computed(() => {
  if (props.tone === "success") {
    return "cui-chip--success";
  }
  if (props.tone === "warning") {
    return "cui-chip--warning";
  }
  if (props.tone === "danger") {
    return "cui-chip--danger";
  }
  return "";
});
</script>
