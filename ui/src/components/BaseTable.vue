<template>
  <div class="overflow-hidden rounded border border-rth-border" :class="tableClass">
    <table class="w-full text-left" :class="compact ? 'text-xs' : 'text-sm'">
      <thead class="bg-rth-panel-muted uppercase text-rth-muted tracking-[0.15em]" :class="compact ? 'text-[10px]' : 'text-xs'">
        <tr>
          <th v-for="header in headers" :key="header" class="px-4 py-3" :class="{ 'sticky top-0 z-10': stickyHeader }">
            {{ header }}
          </th>
        </tr>
      </thead>
      <tbody v-if="normalizedRows.length" class="divide-y divide-rth-border">
        <tr
          v-for="(row, rowIndex) in normalizedRows"
          :key="`row-${rowIndex}`"
          class="bg-rth-panel"
          :class="{ 'bg-rth-panel-muted/60': striped && rowIndex % 2 === 1 }"
        >
          <td v-for="(cell, cellIndex) in row" :key="`cell-${rowIndex}-${cellIndex}`" class="px-4 py-3 text-rth-text">
            {{ cell }}
          </td>
        </tr>
      </tbody>
      <tbody v-else>
        <tr>
          <td class="px-4 py-4 text-rth-muted" :colspan="Math.max(headers.length, 1)">
            {{ emptyState }}
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";

type CellValue = string | number;

type TableRow = Record<string, CellValue> | CellValue[];

const props = withDefaults(
  defineProps<{
    headers: string[];
    rows: TableRow[];
    compact?: boolean;
    striped?: boolean;
    stickyHeader?: boolean;
    emptyState?: string;
  }>(),
  {
    compact: false,
    striped: false,
    stickyHeader: false,
    emptyState: "No records available."
  }
);

const normalizeObjectRow = (row: Record<string, CellValue>): CellValue[] => {
  if (!props.headers.length) {
    return Object.values(row);
  }
  return props.headers.map((header) => {
    if (header in row) {
      return row[header];
    }
    const normalized = header.trim().toLowerCase();
    const matchingKey = Object.keys(row).find((key) => key.trim().toLowerCase() === normalized);
    if (matchingKey) {
      return row[matchingKey];
    }
    return "-";
  });
};

const normalizedRows = computed<CellValue[][]>(() =>
  props.rows.map((row) => (Array.isArray(row) ? row : normalizeObjectRow(row)))
);

const tableClass = computed(() => ({
  "cui-scrollbar": true
}));
</script>
