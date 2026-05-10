<template>
  <Teleport to="body">
    <div v-if="open" class="fixed inset-0 z-50 flex justify-end bg-black/60" @click.self="emit('close')">
      <div
        ref="panelRef"
        class="cui-drawer h-full w-full p-6"
        :class="sizeClass"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="titleId"
        tabindex="-1"
      >
        <header class="flex items-start justify-between gap-3">
          <slot name="header">
            <h3 :id="titleId" class="text-lg font-semibold">{{ title }}</h3>
          </slot>
          <button v-if="!hideClose" class="cui-modal-close" aria-label="Close" @click="emit('close')">X</button>
        </header>

        <div class="mt-4">
          <slot />
        </div>

        <footer v-if="$slots.footer" class="mt-4">
          <slot name="footer" />
        </footer>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { nextTick, onBeforeUnmount, ref, watch } from "vue";

import type { CosmicSize } from "../types/cosmic-ui";

const props = withDefaults(
  defineProps<{
    open: boolean;
    title?: string;
    size?: CosmicSize;
    hideClose?: boolean;
  }>(),
  {
    title: "",
    size: "md",
    hideClose: false
  }
);

const emit = defineEmits<{ (event: "close"): void }>();

const panelRef = ref<HTMLElement | null>(null);
const titleId = `drawer-title-${Math.random().toString(36).slice(2, 8)}`;
const previousFocus = ref<HTMLElement | null>(null);

const sizeClass = computed(() => {
  if (props.size === "xs") {
    return "max-w-sm";
  }
  if (props.size === "sm") {
    return "max-w-md";
  }
  if (props.size === "lg") {
    return "max-w-2xl";
  }
  return "max-w-xl";
});

const focusableSelectors =
  "a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex='-1'])";

const handleKeydown = (event: KeyboardEvent) => {
  if (!props.open) {
    return;
  }
  if (event.key === "Escape") {
    emit("close");
    return;
  }
  if (event.key !== "Tab") {
    return;
  }
  const panel = panelRef.value;
  if (!panel) {
    return;
  }
  const focusable = Array.from(panel.querySelectorAll<HTMLElement>(focusableSelectors));
  if (focusable.length === 0) {
    event.preventDefault();
    return;
  }
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
};

watch(
  () => props.open,
  async (open) => {
    if (open) {
      previousFocus.value = document.activeElement as HTMLElement;
      await nextTick();
      panelRef.value?.focus();
      window.addEventListener("keydown", handleKeydown);
    } else {
      window.removeEventListener("keydown", handleKeydown);
      previousFocus.value?.focus();
    }
  }
);

onBeforeUnmount(() => {
  window.removeEventListener("keydown", handleKeydown);
});
</script>
