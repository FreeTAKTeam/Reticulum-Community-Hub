<template>
  <BasePagination v-model:page="pageModel" :page-size="pageSize" :total="total" />
</template>

<script setup lang="ts">
import { computed } from "vue";

import BasePagination from "../BasePagination.vue";

const props = defineProps<{
  page: number;
  pageSize: number;
  total: number;
}>();

const emit = defineEmits<{ (event: "update:page", value: number): void }>();

const pageModel = computed({
  get: () => props.page,
  set: (value: number) => emit("update:page", value)
});
</script>
