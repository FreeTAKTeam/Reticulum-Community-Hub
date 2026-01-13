<template>
  <div v-if="hasContent" class="max-h-80 overflow-auto rounded border border-rth-border bg-rth-panel-muted p-3">
    <div v-if="renderMode === 'html'" class="rth-markdown" v-html="stringValue"></div>
    <div v-else-if="renderMode === 'markdown'" class="rth-markdown" v-html="markdownHtml"></div>
    <pre v-else class="rth-output-code">{{ jsonText }}</pre>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import MarkdownIt from "markdown-it";

type RenderMode = "auto" | "markdown" | "json" | "html";

const props = withDefaults(
  defineProps<{
    value?: unknown;
    mode?: RenderMode;
  }>(),
  {
    mode: "auto"
  }
);

const md = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true
});

const hasContent = computed(() => {
  if (props.value === undefined || props.value === null) {
    return false;
  }
  if (typeof props.value === "string") {
    return props.value.trim().length > 0;
  }
  return true;
});

const stringValue = computed(() => (typeof props.value === "string" ? props.value : String(props.value ?? "")));

const jsonCandidate = computed(() => {
  if (props.mode === "markdown" || props.mode === "html") {
    return null;
  }
  if (props.mode === "json") {
    return props.value ?? null;
  }
  if (typeof props.value === "string") {
    const trimmed = props.value.trim();
    if ((trimmed.startsWith("{") && trimmed.endsWith("}")) || (trimmed.startsWith("[") && trimmed.endsWith("]"))) {
      try {
        return JSON.parse(trimmed);
      } catch {
        return null;
      }
    }
    return null;
  }
  return props.value ?? null;
});

const renderMode = computed<"html" | "markdown" | "json">(() => {
  if (props.mode === "html") {
    return "html";
  }
  if (props.mode === "markdown") {
    return "markdown";
  }
  if (props.mode === "json") {
    return "json";
  }
  if (jsonCandidate.value !== null && jsonCandidate.value !== undefined) {
    return "json";
  }
  if (typeof props.value === "string") {
    return "markdown";
  }
  return "markdown";
});

const markdownHtml = computed(() => md.render(stringValue.value));

const jsonText = computed(() => {
  const value = jsonCandidate.value;
  if (value === null || value === undefined) {
    return "";
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
});
</script>
