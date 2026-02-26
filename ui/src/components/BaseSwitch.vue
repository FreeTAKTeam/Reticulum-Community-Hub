<template>
  <label class="cui-switch">
    <input class="cui-switch__input" type="checkbox" :checked="modelValue" :disabled="disabled" @change="onChange" />
    <span class="cui-switch__track" aria-hidden="true">
      <span class="cui-switch__indicator"></span>
    </span>
    <span class="cui-switch__label">{{ label }}</span>
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
