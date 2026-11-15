<template>
  <BaseField :label="label" :hint="hint" :state="disabled ? 'disabled' : 'default'" :for-id="id">
    <div class="recipient-picker">
      <div class="cui-field__control recipient-picker__control">
        <input
          :id="id"
          ref="inputRef"
          class="cui-input"
          type="text"
          role="combobox"
          autocomplete="off"
          aria-autocomplete="list"
          :aria-expanded="open"
          :aria-controls="listId"
          :aria-activedescendant="activeIndex >= 0 ? optionId(activeIndex) : undefined"
          :placeholder="placeholder"
          :value="query"
          :disabled="disabled"
          @input="onInput"
          @focus="open = true"
          @keydown="onKeydown"
          @blur="onBlur"
        />
        <button
          v-if="query && !disabled"
          type="button"
          class="recipient-picker__clear"
          aria-label="Clear recipient"
          @mousedown.prevent
          @click="clear"
        >
          ×
        </button>
      </div>
      <ul v-if="open && !disabled" :id="listId" class="recipient-picker__list" role="listbox" :aria-label="label">
        <li v-if="loading && !filtered.length" class="recipient-picker__note" role="presentation">Loading users…</li>
        <li v-else-if="!filtered.length" class="recipient-picker__note" role="presentation">{{ emptyText }}</li>
        <li
          v-for="(option, index) in filtered"
          :id="optionId(index)"
          :key="option.value"
          class="recipient-picker__option"
          :class="{
            'recipient-picker__option--active': index === activeIndex,
            'recipient-picker__option--selected': option.value === modelValue
          }"
          role="option"
          :aria-selected="option.value === modelValue"
          @mousedown.prevent
          @mouseenter="activeIndex = index"
          @click="select(option)"
        >
          <span class="recipient-picker__label">{{ option.label }}</span>
          <span v-if="option.tag" class="recipient-picker__tag">{{ option.tag }}</span>
          <span class="recipient-picker__detail">{{ option.detail }}</span>
        </li>
      </ul>
    </div>
  </BaseField>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import BaseField from "./BaseField.vue";

export interface RecipientOption {
  /** Value emitted when chosen, e.g. an LXMF destination hash. */
  value: string;
  label: string;
  detail?: string;
  tag?: string;
}

const props = withDefaults(
  defineProps<{
    id: string;
    label: string;
    options: RecipientOption[];
    modelValue: string;
    hint?: string;
    placeholder?: string;
    loading?: boolean;
    disabled?: boolean;
    /** Accept typed text as the value when it matches no option (e.g. a raw address). */
    acceptTyped?: (text: string) => string | null;
    maxResults?: number;
  }>(),
  { hint: "", placeholder: "", loading: false, disabled: false, acceptTyped: undefined, maxResults: 50 }
);

const emit = defineEmits<{ (event: "update:modelValue", value: string): void }>();

const inputRef = ref<HTMLInputElement | null>(null);
const open = ref(false);
const activeIndex = ref(-1);
const listId = computed(() => `${props.id}-listbox`);
const optionId = (index: number) => `${props.id}-option-${index}`;

const labelFor = (value: string) => props.options.find((option) => option.value === value)?.label ?? value;
const query = ref(props.modelValue ? labelFor(props.modelValue) : "");

watch(
  () => [props.modelValue, props.options] as const,
  ([value]) => {
    if (value && !open.value) {
      query.value = labelFor(value);
    }
  }
);

const normalized = (text: string) => text.trim().toLowerCase();

const filtered = computed(() => {
  const term = normalized(query.value);
  const selectedLabel = props.modelValue ? labelFor(props.modelValue) : "";
  const showAll = !term || query.value === selectedLabel;
  const matches = showAll
    ? props.options
    : props.options.filter((option) =>
        [option.label, option.detail ?? "", option.value, option.tag ?? ""].some((field) =>
          field.toLowerCase().includes(term)
        )
      );
  return matches.slice(0, props.maxResults);
});

const emptyText = computed(() =>
  props.options.length ? "No users match. You can also paste an LXMF address." : "No users known to this hub yet."
);

watch(filtered, (list) => {
  if (activeIndex.value >= list.length) {
    activeIndex.value = list.length ? 0 : -1;
  }
});

const onInput = (event: Event) => {
  query.value = (event.target as HTMLInputElement).value;
  open.value = true;
  activeIndex.value = filtered.value.length ? 0 : -1;
  emit("update:modelValue", props.acceptTyped?.(query.value) ?? "");
};

const select = (option: RecipientOption) => {
  query.value = option.label;
  open.value = false;
  activeIndex.value = -1;
  emit("update:modelValue", option.value);
};

const clear = () => {
  query.value = "";
  emit("update:modelValue", "");
  open.value = true;
  inputRef.value?.focus();
};

const onKeydown = (event: KeyboardEvent) => {
  const count = filtered.value.length;
  if (event.key === "ArrowDown") {
    event.preventDefault();
    open.value = true;
    activeIndex.value = count ? (activeIndex.value + 1) % count : -1;
  } else if (event.key === "ArrowUp") {
    event.preventDefault();
    open.value = true;
    activeIndex.value = count ? (activeIndex.value - 1 + count) % count : -1;
  } else if (event.key === "Enter" && open.value && activeIndex.value >= 0 && activeIndex.value < count) {
    event.preventDefault();
    select(filtered.value[activeIndex.value]);
  } else if (event.key === "Escape" && open.value) {
    event.preventDefault();
    event.stopPropagation();
    open.value = false;
  }
};

const onBlur = () => {
  open.value = false;
  if (props.modelValue && !props.acceptTyped?.(query.value)) {
    query.value = labelFor(props.modelValue);
  }
};
</script>

<style scoped>
.recipient-picker {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.recipient-picker__control {
  position: relative;
}

.recipient-picker__clear {
  position: absolute;
  right: 8px;
  top: 50%;
  transform: translateY(-50%);
  width: 28px;
  height: 28px;
  border: 0;
  background: transparent;
  color: var(--cui-muted);
  font-size: 18px;
  cursor: pointer;
}

.recipient-picker__clear:hover,
.recipient-picker__clear:focus-visible {
  color: var(--cui-text);
}

.recipient-picker__list {
  margin: 0;
  padding: 4px;
  list-style: none;
  max-height: 240px;
  overflow-y: auto;
  border: 1px solid var(--cui-border);
  background: var(--cui-panel);
}

.recipient-picker__option {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 2px 8px;
  padding: 8px 10px;
  cursor: pointer;
  color: var(--cui-text);
}

.recipient-picker__option--active {
  background: var(--cui-accent-soft);
}

.recipient-picker__option--selected .recipient-picker__label {
  color: var(--cui-primary);
}

.recipient-picker__label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.recipient-picker__tag {
  align-self: center;
  padding: 1px 6px;
  border: 1px solid var(--cui-border);
  font-size: 0.7rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--cui-muted);
}

.recipient-picker__detail {
  grid-column: 1 / -1;
  font-family: "JetBrains Mono", monospace;
  font-size: 0.75rem;
  color: var(--cui-muted);
  overflow: hidden;
  text-overflow: ellipsis;
}

.recipient-picker__note {
  padding: 8px 10px;
  color: var(--cui-muted);
  font-size: 0.85rem;
}
</style>
