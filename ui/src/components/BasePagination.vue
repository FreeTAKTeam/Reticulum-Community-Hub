<template>
  <div v-if="totalPages > 1" class="flex flex-wrap items-center justify-between gap-3 text-xs text-rth-muted">
    <div>Showing {{ start }}-{{ end }} of {{ total }}</div>
    <div class="flex items-center gap-2">
      <BaseButton variant="secondary" :disabled="page <= 1" @click="goPrevious">Prev</BaseButton>
      <span>Page {{ page }} of {{ totalPages }}</span>
      <BaseButton variant="secondary" :disabled="page >= totalPages" @click="goNext">Next</BaseButton>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import BaseButton from "./BaseButton.vue";

const props = defineProps<{ page: number; pageSize: number; total: number }>();
const emit = defineEmits<{ (event: "update:page", value: number): void }>();

const totalPages = computed(() => Math.max(1, Math.ceil(props.total / props.pageSize)));
const start = computed(() => (props.total === 0 ? 0 : (props.page - 1) * props.pageSize + 1));
const end = computed(() => Math.min(props.page * props.pageSize, props.total));

const goPrevious = () => emit("update:page", Math.max(1, props.page - 1));
const goNext = () => emit("update:page", Math.min(totalPages.value, props.page + 1));
</script>
