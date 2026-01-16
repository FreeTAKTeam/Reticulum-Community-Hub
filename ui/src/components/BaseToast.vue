<template>
  <div class="fixed bottom-6 right-6 z-50 flex w-full max-w-sm flex-col gap-3">
    <div
      v-for="toast in toastStore.messages"
      :key="toast.id"
      class="relative overflow-hidden rounded-xl border border-rth-border px-4 py-3 text-sm shadow-[0_12px_30px_rgba(7,10,20,0.55)] backdrop-blur"
      :class="toneShellClass(toast.tone)"
    >
      <span class="pointer-events-none absolute inset-x-0 top-0 h-px opacity-80" :class="toneLineClass(toast.tone)"></span>
      <span class="pointer-events-none absolute inset-y-0 left-0 w-[3px]" :class="toneAccentClass(toast.tone)"></span>
      <span class="pointer-events-none absolute -right-6 -top-6 h-16 w-16 rotate-45 rounded-lg border border-rth-border bg-rth-panel-muted/70"></span>
      <div class="relative flex items-start gap-3">
        <div
          class="mt-0.5 flex h-7 w-7 items-center justify-center rounded-md border border-rth-border bg-rth-panel-muted"
          :class="toneIconClass(toast.tone)"
        >
          <svg v-if="toast.tone === 'success'" viewBox="0 0 24 24" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M9 12l2 2 4-4"></path>
            <path d="M12 3a9 9 0 1 1 0 18a9 9 0 0 1 0-18z"></path>
          </svg>
          <svg v-else-if="toast.tone === 'warning'" viewBox="0 0 24 24" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M10.29 3.86l-7.4 12.8a1 1 0 0 0 .86 1.5h14.5a1 1 0 0 0 .86-1.5l-7.4-12.8a1 1 0 0 0-1.72 0z"></path>
            <path d="M12 9v4"></path>
            <path d="M12 17h.01"></path>
          </svg>
          <svg v-else-if="toast.tone === 'error' || toast.tone === 'danger'" viewBox="0 0 24 24" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M9 9l6 6"></path>
            <path d="M15 9l-6 6"></path>
            <path d="M12 3a9 9 0 1 1 0 18a9 9 0 0 1 0-18z"></path>
          </svg>
          <svg v-else viewBox="0 0 24 24" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M12 8h.01"></path>
            <path d="M11 12h2v5h-2z"></path>
            <path d="M12 3a9 9 0 1 1 0 18a9 9 0 0 1 0-18z"></path>
          </svg>
        </div>
        <div class="font-semibold leading-snug" :class="toneTextClass(toast.tone)">
          {{ toast.message }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useToastStore } from "../stores/toasts";

const toastStore = useToastStore();

const toneShellClass = (tone: string) => {
  if (tone === "success") {
    return "bg-[linear-gradient(135deg,#101b2a_0%,#0f1724_45%,#0f1320_100%)] shadow-[0_0_0_1px_rgba(63,208,255,0.25),0_12px_30px_rgba(7,10,20,0.6)]";
  }
  if (tone === "warning") {
    return "bg-[linear-gradient(135deg,#1e1a0f_0%,#141828_55%,#0f1320_100%)] shadow-[0_0_0_1px_rgba(245,158,11,0.25),0_12px_30px_rgba(7,10,20,0.6)]";
  }
  if (tone === "error" || tone === "danger") {
    return "bg-[linear-gradient(135deg,#251216_0%,#141828_55%,#0f1320_100%)] shadow-[0_0_0_1px_rgba(239,68,68,0.28),0_12px_30px_rgba(7,10,20,0.6)]";
  }
  return "bg-[linear-gradient(135deg,#141e31_0%,#141828_55%,#0f1320_100%)] shadow-[0_0_0_1px_rgba(77,182,255,0.2),0_12px_30px_rgba(7,10,20,0.6)]";
};

const toneLineClass = (tone: string) => {
  if (tone === "success") {
    return "bg-[linear-gradient(90deg,rgba(63,208,255,0.85),rgba(63,208,255,0))]";
  }
  if (tone === "warning") {
    return "bg-[linear-gradient(90deg,rgba(245,158,11,0.9),rgba(245,158,11,0))]";
  }
  if (tone === "error" || tone === "danger") {
    return "bg-[linear-gradient(90deg,rgba(239,68,68,0.85),rgba(239,68,68,0))]";
  }
  return "bg-[linear-gradient(90deg,rgba(77,182,255,0.85),rgba(77,182,255,0))]";
};

const toneAccentClass = (tone: string) => {
  if (tone === "success") {
    return "bg-[#3fd0ff]";
  }
  if (tone === "warning") {
    return "bg-[#f59e0b]";
  }
  if (tone === "error" || tone === "danger") {
    return "bg-[#ef4444]";
  }
  return "bg-[#4db6ff]";
};

const toneIconClass = (tone: string) => {
  if (tone === "success") {
    return "text-[#76d7ff]";
  }
  if (tone === "warning") {
    return "text-[#fbbf24]";
  }
  if (tone === "error" || tone === "danger") {
    return "text-[#f87171]";
  }
  return "text-[#8fd4ff]";
};

const toneTextClass = (tone: string) => {
  if (tone === "success") {
    return "text-[#c8f1ff]";
  }
  if (tone === "warning") {
    return "text-[#fde68a]";
  }
  if (tone === "error" || tone === "danger") {
    return "text-[#fecaca]";
  }
  return "text-rth-text";
};
</script>
