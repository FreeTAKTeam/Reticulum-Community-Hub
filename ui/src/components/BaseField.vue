<template>
  <div class="cui-field" :class="fieldClass">
    <div v-if="label" class="cui-field__label-row">
      <label class="cui-field__label" :for="forId">
        {{ label }}
        <span v-if="required" class="cui-field__required" aria-hidden="true">*</span>
      </label>
    </div>

    <slot />

    <p v-if="error" class="cui-field__error">{{ error }}</p>
    <p v-else-if="hint" class="cui-field__hint">{{ hint }}</p>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";

import type { CosmicFieldState } from "../types/cosmic-ui";
import type { CosmicSize } from "../types/cosmic-ui";

const props = withDefaults(
  defineProps<{
    label?: string;
    hint?: string;
    error?: string;
    required?: boolean;
    state?: CosmicFieldState;
    size?: CosmicSize;
    forId?: string;
  }>(),
  {
    label: "",
    hint: "",
    error: "",
    required: false,
    state: "default",
    size: "md",
    forId: ""
  }
);

const fieldClass = computed(() => [
  props.error || props.state === "invalid" ? "is-invalid" : "",
  props.state === "disabled" ? "is-disabled" : "",
  props.state === "readonly" ? "is-readonly" : "",
  props.state === "focus" ? "is-focus" : "",
  props.size === "xs" ? "cui-field--xs" : "",
  props.size === "sm" ? "cui-field--sm" : "",
  props.size === "lg" ? "cui-field--lg" : ""
]);
</script>
