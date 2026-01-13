<template>
  <div class="flex flex-col gap-1">
    <label v-if="label" class="text-xs text-rth-muted">{{ label }}</label>
    <input :type="type" :value="modelValue" class="rounded border border-rth-border bg-rth-panel-muted px-3 py-2 text-sm text-rth-text focus:border-rth-accent focus:outline-none" @input="onInput" />
  </div>
</template>

<script setup lang="ts">
const props = withDefaults(defineProps<{ label?: string; type?: string; modelValue?: string }>(), {
  type: "text",
  modelValue: ""
});

const emit = defineEmits<{ (event: "update:modelValue", value: string): void }>();

const onInput = (event: Event) => {
  const target = event.target as HTMLInputElement;
  emit("update:modelValue", target.value);
};
</script>
