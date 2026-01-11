<template>
  <div class="flex flex-col gap-1">
    <label v-if="label" class="text-xs text-slate-400">{{ label }}</label>
    <select :value="modelValue" class="rounded border border-rth-border bg-slate-900 px-3 py-2 text-sm text-slate-100" @change="onChange">
      <option v-for="option in options" :key="option.value" :value="option.value">
        {{ option.label }}
      </option>
    </select>
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
