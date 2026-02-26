<template>
  <BaseTable
    :headers="headers"
    :rows="rows"
    :compact="compact"
    :striped="striped"
    :sticky-header="stickyHeader"
    :empty-state="emptyState"
  />
</template>

<script setup lang="ts">
import BaseTable from "../BaseTable.vue";

defineProps<{
  headers: string[];
  rows: Array<Record<string, string | number> | Array<string | number>>;
  compact?: boolean;
  striped?: boolean;
  stickyHeader?: boolean;
  emptyState?: string;
}>();
</script>
