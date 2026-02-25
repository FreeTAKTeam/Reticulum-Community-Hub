<template>
  <div class="border border-rth-border bg-rth-panel-muted px-3 py-2 text-sm" :class="bannerClass">
    <slot>{{ message }}</slot>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";

const props = withDefaults(
  defineProps<{
    message?: string;
    tone?: "info" | "success" | "warning" | "danger";
  }>(),
  {
    message: "",
    tone: "info"
  }
);

const bannerClass = computed(() => {
  if (props.tone === "success") {
    return "text-[#8ff0dd]";
  }
  if (props.tone === "warning") {
    return "text-[#fcd34d]";
  }
  if (props.tone === "danger") {
    return "text-[#fecaca]";
  }
  return "text-rth-text";
});
</script>
