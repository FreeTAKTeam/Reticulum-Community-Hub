<template>
  <div class="panel-tabs">
    <button
      v-for="option in options"
      :key="option.value"
      class="panel-tab"
      :class="{ active: option.value === modelValue }"
      type="button"
      @click="emit('update:modelValue', option.value)"
    >
      {{ option.label }}
    </button>
  </div>
</template>

<script setup lang="ts">
interface TabOption {
  label: string;
  value: string;
}

defineProps<{
  options: TabOption[];
  modelValue: string;
}>();

const emit = defineEmits<{ (event: "update:modelValue", value: string): void }>();
</script>
