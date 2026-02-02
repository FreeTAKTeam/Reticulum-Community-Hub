<template>
  <div class="space-y-3">
    <div v-if="!modelValue.length" class="text-xs text-rth-muted">{{ emptyLabel }}</div>
    <div v-for="(entry, index) in modelValue" :key="`${index}-${entry.key}`" class="grid gap-2 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
      <input
        :value="entry.key"
        type="text"
        class="cui-input"
        :placeholder="keyPlaceholder"
        @input="updateEntry(index, 'key', ($event.target as HTMLInputElement).value)"
      />
      <input
        :value="entry.value"
        type="text"
        class="cui-input"
        :placeholder="valuePlaceholder"
        @input="updateEntry(index, 'value', ($event.target as HTMLInputElement).value)"
      />
      <BaseButton
        variant="secondary"
        size="sm"
        icon-left="trash"
        icon-only
        aria-label="Remove setting"
        @click="removeEntry(index)"
      />
    </div>
    <BaseButton variant="secondary" size="sm" icon-left="plus" @click="addEntry">
      Add setting
    </BaseButton>
  </div>
</template>

<script setup lang="ts">
import BaseButton from "./BaseButton.vue";
import type { KeyValueItem } from "../utils/reticulum-config";

const props = withDefaults(
  defineProps<{
    modelValue: KeyValueItem[];
    emptyLabel?: string;
    keyPlaceholder?: string;
    valuePlaceholder?: string;
  }>(),
  {
    emptyLabel: "No settings defined yet.",
    keyPlaceholder: "Key",
    valuePlaceholder: "Value"
  }
);

const emit = defineEmits<{ (event: "update:modelValue", value: KeyValueItem[]): void }>();

const updateEntry = (index: number, field: "key" | "value", value: string) => {
  const next = props.modelValue.map((item, idx) =>
    idx === index ? { ...item, [field]: value } : item
  );
  emit("update:modelValue", next);
};

const addEntry = () => {
  emit("update:modelValue", [...props.modelValue, { key: "", value: "" }]);
};

const removeEntry = (index: number) => {
  const next = props.modelValue.filter((_, idx) => idx !== index);
  emit("update:modelValue", next);
};
</script>
