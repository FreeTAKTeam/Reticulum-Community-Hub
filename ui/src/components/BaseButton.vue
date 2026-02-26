<template>
  <button
    :type="type"
    class="cui-btn inline-flex items-center justify-center gap-2 font-semibold tracking-[0.02em]"
    :class="buttonClass"
    :disabled="isDisabled"
    :aria-label="computedAriaLabel"
    :aria-busy="loading ? 'true' : undefined"
  >
    <span v-if="loading" class="cui-btn__icon" aria-hidden="true" v-html="spinnerSvg"></span>
    <span v-else-if="iconLeftSvg" class="cui-btn__icon" aria-hidden="true" v-html="iconLeftSvg"></span>
    <span v-if="!iconOnly" class="cui-btn__label"><slot /></span>
    <span v-if="!loading && iconRightSvg" class="cui-btn__icon" aria-hidden="true" v-html="iconRightSvg"></span>
  </button>
</template>

<script setup lang="ts">
import { computed } from "vue";

import type { CosmicSize } from "../types/cosmic-ui";
import type { CosmicTone } from "../types/cosmic-ui";

type ButtonVariant = "primary" | "secondary" | "ghost" | "success" | "danger" | "tab";

type ButtonIconName =
  | "refresh"
  | "plus"
  | "edit"
  | "trash"
  | "check"
  | "download"
  | "ban"
  | "unban"
  | "blackhole"
  | "filter"
  | "eye"
  | "save"
  | "link"
  | "upload"
  | "undo"
  | "send"
  | "route"
  | "users"
  | "help"
  | "list"
  | "chevron-left"
  | "chevron-right"
  | "layers"
  | "file"
  | "image"
  | "fingerprint"
  | "settings"
  | "tool"
  | "play"
  | "stop";

const props = withDefaults(
  defineProps<{
    variant?: ButtonVariant;
    tone?: CosmicTone;
    type?: "button" | "submit" | "reset";
    size?: CosmicSize;
    iconLeft?: ButtonIconName;
    iconRight?: ButtonIconName;
    iconOnly?: boolean;
    ariaLabel?: string;
    loading?: boolean;
    disabled?: boolean;
  }>(),
  {
    variant: "primary",
    tone: "primary",
    type: "button",
    size: "md",
    iconLeft: undefined,
    iconRight: undefined,
    iconOnly: false,
    ariaLabel: undefined,
    loading: false,
    disabled: false
  }
);

const variantClass = computed(() => {
  if (props.variant === "ghost") {
    return "cui-btn--ghost";
  }
  if (props.variant === "secondary") {
    return "cui-btn--secondary";
  }
  if (props.variant === "success") {
    return "cui-btn--success";
  }
  if (props.variant === "danger") {
    return "cui-btn--danger";
  }
  if (props.variant === "tab") {
    return "cui-btn--tab";
  }
  return "cui-btn--primary";
});

const sizeClass = computed(() => {
  if (props.size === "xs") {
    return "cui-btn--xs";
  }
  if (props.size === "sm") {
    return "cui-btn--sm";
  }
  if (props.size === "lg") {
    return "cui-btn--lg";
  }
  return "cui-btn--md";
});

const toneClass = computed(() => {
  if (!props.tone) {
    return "";
  }
  return `cui-tone-${props.tone}`;
});

const isDisabled = computed(() => props.disabled || props.loading);

const buttonClass = computed(() => [
  variantClass.value,
  sizeClass.value,
  toneClass.value,
  props.variant === "tab" ? "" : "cui-btn--action",
  props.iconOnly ? "cui-btn--icon-only" : "",
  props.loading ? "is-loading" : ""
]);

const spinnerSvg =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9" opacity="0.28"></circle><path d="M21 12a9 9 0 0 1-9 9"/></svg>';

const iconMap: Record<ButtonIconName, string> = {
  refresh:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-2.64-6.36"/><polyline points="21 3 21 9 15 9"/></svg>',
  plus:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>',
  edit:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 1 1 3 3L7 19l-4 1 1-4Z"/></svg>',
  trash:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4h6v2"/></svg>',
  check:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="m9 12 2 2 4-4"/></svg>',
  download:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M7 10l5 5 5-5"/><path d="M12 15V3"/></svg>',
  ban:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M5 5l14 14"/></svg>',
  unban:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="m8 12 2 2 5-5"/></svg>',
  blackhole:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="2" fill="currentColor" stroke="none"/></svg>',
  filter:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 4h18l-7 8v6l-4 2v-8Z"/></svg>',
  eye:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s4-6 10-6 10 6 10 6-4 6-10 6-10-6-10-6Z"/><circle cx="12" cy="12" r="3"/></svg>',
  save:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2Z"/><path d="M17 21v-8H7v8"/><path d="M7 3v5h8"/></svg>',
  link:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.07 0l2.83-2.83a5 5 0 0 0-7.07-7.07L11 4"/><path d="M14 11a5 5 0 0 0-7.07 0L4.1 13.83a5 5 0 1 0 7.07 7.07L13 20"/></svg>',
  upload:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M17 8l-5-5-5 5"/><path d="M12 3v12"/></svg>',
  undo:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 14l-4-4 4-4"/><path d="M5 10h9a5 5 0 1 1 0 10H9"/></svg>',
  send:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 2 11 13"/><path d="M22 2 15 22l-4-9-9-4 20-7Z"/></svg>',
  route:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="6" cy="18" r="3"/><circle cx="18" cy="6" r="3"/><path d="M8.5 16.5 15.5 9.5"/><path d="M6 6h6"/><path d="M18 18h-6"/></svg>',
  users:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
  help:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 2-3 4"/><path d="M12 17h.01"/></svg>',
  list:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><circle cx="3" cy="6" r="1"/><circle cx="3" cy="12" r="1"/><circle cx="3" cy="18" r="1"/></svg>',
  "chevron-left":
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg>',
  "chevron-right":
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>',
  layers:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 22 8 12 14 2 8 12 2"/><path d="M2 12l10 6 10-6"/><path d="M2 16l10 6 10-6"/></svg>',
  file:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6"/></svg>',
  image:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/></svg>',
  fingerprint:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 11a2 2 0 0 1 2 2c0 2.5 0 4 2 5"/><path d="M8 11a4 4 0 0 1 8 0c0 3 0 6 3 8"/><path d="M6 11a6 6 0 0 1 12 0c0 4-1 7 2 10"/><path d="M10 11a2 2 0 0 0-2 2c0 2 0 3-1 4"/><path d="M4 11a8 8 0 0 1 16 0"/></svg>',
  settings:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1 1.56V21a2 2 0 0 1-4 0v-.08a1.7 1.7 0 0 0-1-1.56 1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-1.56-1H3a2 2 0 0 1 0-4h.08a1.7 1.7 0 0 0 1.56-1 1.7 1.7 0 0 0-.34-1.87l-.06-.06A2 2 0 0 1 7.07 4.2l.06.06A1.7 1.7 0 0 0 9 4.6 1.7 1.7 0 0 0 10 3.04V3a2 2 0 0 1 4 0v.08a1.7 1.7 0 0 0 1 1.56 1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.7 1.7 0 0 0 19.4 9c.1.38.14.78.14 1.2s-.04.82-.14 1.2z"/></svg>',
  tool:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 7a5 5 0 0 0-6.83 6.83l-4.2 4.2a2 2 0 0 0 2.83 2.83l4.2-4.2A5 5 0 0 0 17 10l-3 3-2-2 3-3z"/></svg>',
  play:
    '<svg viewBox="0 0 24 24" fill="currentColor" stroke="none"><path d="M8 5v14l11-7z"/></svg>',
  stop:
    '<svg viewBox="0 0 24 24" fill="currentColor" stroke="none"><rect x="7" y="7" width="10" height="10" rx="1.5"/></svg>'
};

const iconLeftSvg = computed(() => (props.iconLeft ? iconMap[props.iconLeft] : undefined));
const iconRightSvg = computed(() => (props.iconRight ? iconMap[props.iconRight] : undefined));
const computedAriaLabel = computed(() => (props.iconOnly ? props.ariaLabel : undefined));
</script>
