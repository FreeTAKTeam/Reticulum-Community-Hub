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
    <div class="cui-field__control">
      <input
        :id="id"
        class="cui-input"
        :type="type"
        :name="name"
        :value="modelValue"
        :placeholder="placeholder"
        :disabled="disabled"
        :readonly="readonly"
        @input="onInput"
      />
    </div>
  </BaseField>
</template>

<script setup lang="ts">
import { computed } from "vue";

import BaseField from "./BaseField.vue";
import type { CosmicFieldState } from "../types/cosmic-ui";
import type { CosmicSize } from "../types/cosmic-ui";

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
    type?: string;
    modelValue?: string;
    placeholder?: string;
    disabled?: boolean;
    readonly?: boolean;
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
    type: "text",
    modelValue: "",
    placeholder: "",
    disabled: false,
    readonly: false
  }
);

const emit = defineEmits<{ (event: "update:modelValue", value: string): void }>();

const resolvedState = computed<CosmicFieldState>(() => {
  if (props.disabled) {
    return "disabled";
  }
  if (props.readonly) {
    return "readonly";
  }
  if (props.error) {
    return "invalid";
  }
  return props.state;
});

const onInput = (event: Event) => {
  const target = event.target as HTMLInputElement;
  emit("update:modelValue", target.value);
};
</script>
