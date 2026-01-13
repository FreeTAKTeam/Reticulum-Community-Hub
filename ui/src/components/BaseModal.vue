<template>
  <div v-if="open" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60" @click.self="emit('close')">
    <div
      ref="panelRef"
      class="w-full max-w-xl rounded border border-rth-border bg-rth-panel p-6"
      role="dialog"
      aria-modal="true"
      :aria-labelledby="titleId"
      tabindex="-1"
    >
      <div class="flex items-start justify-between">
        <h3 :id="titleId" class="text-lg font-semibold">{{ title }}</h3>
        <button class="text-rth-muted hover:text-rth-text" aria-label="Close" @click="emit('close')">X</button>
      </div>
      <div class="mt-4">
        <slot />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from "vue";

const props = defineProps<{ open: boolean; title: string }>();
const emit = defineEmits<{ (event: "close"): void }>();

const panelRef = ref<HTMLElement | null>(null);
const titleId = `modal-title-${Math.random().toString(36).slice(2, 8)}`;
const previousFocus = ref<HTMLElement | null>(null);

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
