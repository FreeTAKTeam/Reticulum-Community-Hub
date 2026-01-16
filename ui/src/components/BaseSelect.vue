<template>
  <div class="cui-combobox">
    <label v-if="label" class="cui-combobox__label">{{ label }}</label>
    <div class="cui-combobox__control">
      <select :value="modelValue" class="cui-combobox__select" @change="onChange">
        <option v-for="option in options" :key="option.value" :value="option.value">
          {{ option.label }}
        </option>
      </select>
      <span class="cui-combobox__chevron" aria-hidden="true"></span>
    </div>
  </div>
</template>

<script setup lang="ts">
interface OptionItem {
  label: string;
  value: string;
}

const props = defineProps<{ label?: string; options: OptionItem[]; modelValue?: string }>();
const emit = defineEmits<{ (event: "update:modelValue", value: string): void }>();

const onChange = (event: Event) => {
  const target = event.target as HTMLSelectElement;
  emit("update:modelValue", target.value);
};
</script>
