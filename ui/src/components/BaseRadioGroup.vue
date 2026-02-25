<template>
  <BaseField :label="label" :hint="hint" :error="error" :required="required" :state="state" :size="size">
    <div class="grid gap-2">
      <label v-for="option in options" :key="option.value" class="inline-flex items-center gap-2 text-sm text-rth-text" :class="{ 'opacity-60': disabled }">
        <input
          class="h-4 w-4 border border-rth-border bg-rth-panel-muted"
          type="radio"
          :name="name"
          :value="option.value"
          :checked="String(modelValue) === String(option.value)"
          :disabled="disabled"
          @change="onChange"
        />
        <span>{{ option.label }}</span>
      </label>
    </div>
  </BaseField>
</template>

<script setup lang="ts">
import BaseField from "./BaseField.vue";
import type { CosmicFieldState } from "../types/cosmic-ui";
import type { CosmicSize } from "../types/cosmic-ui";

interface RadioOption {
  label: string;
  value: string | number;
}

const props = withDefaults(
  defineProps<{
    name?: string;
    label?: string;
    hint?: string;
    error?: string;
    required?: boolean;
    state?: CosmicFieldState;
    size?: CosmicSize;
    options: RadioOption[];
    modelValue?: string | number;
    disabled?: boolean;
  }>(),
  {
    name: "",
    label: "",
    hint: "",
    error: "",
    required: false,
    state: "default",
    size: "md",
    modelValue: "",
    disabled: false
  }
);

const emit = defineEmits<{ (event: "update:modelValue", value: string): void }>();

const onChange = (event: Event) => {
  const target = event.target as HTMLInputElement;
  emit("update:modelValue", target.value);
};
</script>
