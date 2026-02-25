<template>
  <BaseField
    :label="label"
    :hint="hint"
    :error="error"
    :required="required"
    :state="resolvedState"
    :size="size"
    :for-id="id"
  >
    <div class="cui-combobox__control">
      <select :id="id" :name="name" :value="modelValue" class="cui-combobox__select" :disabled="disabled" @change="onChange">
        <option v-for="option in options" :key="option.value" :value="option.value">
          {{ option.label }}
        </option>
      </select>
      <span class="cui-combobox__chevron" aria-hidden="true"></span>
    </div>
  </BaseField>
</template>

<script setup lang="ts">
import { computed } from "vue";

import BaseField from "./BaseField.vue";
import type { CosmicFieldState } from "../types/cosmic-ui";
import type { CosmicSize } from "../types/cosmic-ui";

interface OptionItem {
  label: string;
  value: string | number;
}

const props = withDefaults(
  defineProps<{
    id?: string;
    name?: string;
    label?: string;
    hint?: string;
    error?: string;
    required?: boolean;
    state?: CosmicFieldState;
    size?: CosmicSize;
    options: OptionItem[];
    modelValue?: string | number;
    disabled?: boolean;
  }>(),
  {
    id: "",
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

const resolvedState = computed<CosmicFieldState>(() => {
  if (props.disabled) {
    return "disabled";
  }
  if (props.error) {
    return "invalid";
  }
  return props.state;
});

const onChange = (event: Event) => {
  const target = event.target as HTMLSelectElement;
  emit("update:modelValue", target.value);
};
</script>
