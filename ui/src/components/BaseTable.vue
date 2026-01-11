<template>
  <div class="overflow-hidden rounded border border-rth-border">
    <table class="w-full text-left text-sm">
      <thead class="bg-slate-900 text-xs uppercase text-slate-400">
        <tr>
          <th v-for="header in headers" :key="header" class="px-4 py-3">
            {{ header }}
          </th>
        </tr>
      </thead>
      <tbody class="divide-y divide-rth-border">
        <tr v-for="(row, index) in rows" :key="index" class="bg-rth-panel">
          <td v-for="cell in row" :key="cell" class="px-4 py-3 text-slate-200">
            {{ cell }}
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
interface TableRow {
  [key: string]: string | number;
}

defineProps<{ headers: string[]; rows: Array<Array<string | number> | TableRow> }>();
</script>
