<template>
  <article class="kpi-card">
    <strong class="kpi-value">{{ value }}</strong>
    <span class="kpi-label">{{ label }}</span>
  </article>
</template>

<script setup lang="ts">
defineProps<{
  label: string;
  value: string | number;
}>();
</script>
