<template>
  <nav aria-label="Breadcrumb" class="flex items-center gap-2 text-xs uppercase tracking-[0.16em] text-rth-muted">
    <template v-for="(item, index) in items" :key="`${item.label}-${index}`">
      <button v-if="item.action" type="button" class="hover:text-rth-text" @click="item.action()">{{ item.label }}</button>
      <span v-else>{{ item.label }}</span>
      <span v-if="index < items.length - 1">/</span>
    </template>
  </nav>
</template>

<script setup lang="ts">
interface BreadcrumbItem {
  label: string;
  action?: () => void;
}

defineProps<{
  items: BreadcrumbItem[];
}>();
</script>
