<template>
  <label class="inline-flex items-center gap-2 text-sm text-rth-text" :class="{ 'opacity-60': disabled }">
    <input
      class="h-4 w-4 rounded border border-rth-border bg-rth-panel-muted"
      type="checkbox"
      :checked="modelValue"
      :disabled="disabled"
      @change="onChange"
    />
    <span>{{ label }}</span>
  </label>
</template>

<script setup lang="ts">
const props = withDefaults(
  defineProps<{
    label?: string;
    modelValue?: boolean;
    disabled?: boolean;
  }>(),
  {
    label: "",
    modelValue: false,
    disabled: false
  }
);

const emit = defineEmits<{ (event: "update:modelValue", value: boolean): void }>();

const onChange = (event: Event) => {
  const target = event.target as HTMLInputElement;
  emit("update:modelValue", target.checked);
};
</script>
