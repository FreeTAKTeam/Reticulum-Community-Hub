<template>
  <div class="cui-combobox">
    <label v-if="label" class="cui-combobox__label">{{ label }}</label>
    <div class="cui-combobox__control">
      <select :value="modelValue" class="cui-combobox__select" @change="onChange">
        <option value="" disabled>Pick an interface type...</option>
        <optgroup v-for="group in groups" :key="group.label" :label="group.label">
          <option v-for="option in group.options" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </optgroup>
      </select>
      <span class="cui-combobox__chevron" aria-hidden="true"></span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { ReticulumInterfaceCapabilities } from "../api/types";
import { getCreatableInterfaceTypeGroups } from "../utils/reticulum-interface-schema";

type OptionGroup = {
  label: string;
  options: { label: string; value: string }[];
};

const props = withDefaults(
  defineProps<{
    modelValue: string;
    label?: string;
    capabilities?: ReticulumInterfaceCapabilities | null;
    allowUnknownCurrentValue?: boolean;
  }>(),
  {
    label: "Type",
    capabilities: null,
    allowUnknownCurrentValue: true,
  }
);

const emit = defineEmits<{ (event: "update:modelValue", value: string): void }>();

const groups = computed<OptionGroup[]>(() => {
  const runtimeGroups = getCreatableInterfaceTypeGroups(props.capabilities).map((group) => ({
    label: group.label,
    options: group.options.map((option) => ({ label: option.label, value: option.value })),
  }));
  const knownTypes = new Set(runtimeGroups.flatMap((group) => group.options.map((option) => option.value)));
  if (
    props.allowUnknownCurrentValue &&
    props.modelValue &&
    !knownTypes.has(props.modelValue)
  ) {
    runtimeGroups.push({
      label: "Existing / Unsupported",
      options: [{ label: props.modelValue, value: props.modelValue }],
    });
  }
  return runtimeGroups;
});

const onChange = (event: Event) => {
  const target = event.target as HTMLSelectElement;
  emit("update:modelValue", target.value);
};
</script>
