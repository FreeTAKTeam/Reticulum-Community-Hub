<template>
  <div v-if="hasContent" class="max-h-80 overflow-auto rounded border border-rth-border bg-rth-panel-muted p-3">
    <div v-if="renderMode === 'html'" class="rth-markdown" v-html="stringValue"></div>
    <div v-else-if="renderMode === 'markdown'" class="rth-markdown" v-html="markdownHtml"></div>
    <div v-else-if="showAccordion" class="cui-json-output">
      <div v-for="section in jsonSections" :key="section.key" class="cui-accordion">
        <details :open="section.open">
          <summary class="cui-accordion__summary">
            <span class="cui-accordion__title">{{ section.title }}</span>
            <span class="cui-accordion__meta">{{ section.meta }}</span>
            <svg class="cui-accordion__chevron" viewBox="0 0 24 24" aria-hidden="true">
              <path d="M6 9l6 6 6-6" fill="none" stroke="currentColor" stroke-width="2" />
            </svg>
          </summary>
          <div class="cui-accordion__body">
            <div v-for="row in section.rows" :key="`${section.key}-${row.label}`" class="cui-json-row">
              <div class="cui-json-key">{{ row.label }}</div>
              <div class="cui-json-value">{{ row.value }}</div>
            </div>
          </div>
        </details>
      </div>
    </div>
    <pre v-else class="rth-output-code">{{ jsonText }}</pre>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import MarkdownIt from "markdown-it";

type RenderMode = "auto" | "markdown" | "json" | "html";

type JsonRow = {
  label: string;
  value: string;
};

type JsonSection = {
  key: string;
  title: string;
  meta: string;
  rows: JsonRow[];
  open: boolean;
};

const props = withDefaults(
  defineProps<{
    value?: unknown;
    mode?: RenderMode;
    accordionOpenByDefault?: boolean;
  }>(),
  {
    mode: "auto",
    accordionOpenByDefault: true
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

const formatLabel = (raw: string) => {
  const spaced = raw
    .replace(/[_-]+/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .trim();
  if (!spaced) {
    return "Value";
  }
  return spaced.replace(/\b\w/g, (char) => char.toUpperCase());
};

const formatPrimitive = (value: unknown) => {
  if (value === null || value === undefined) {
    return "Not set";
  }
  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }
  if (typeof value === "number") {
    return Number.isFinite(value) ? value.toString() : "Not set";
  }
  if (typeof value === "string") {
    return value.trim().length ? value : "Not set";
  }
  return String(value);
};

const isPrimitive = (value: unknown) => {
  return value === null || value === undefined || ["string", "number", "boolean"].includes(typeof value);
};

const flattenRows = (value: unknown, prefix = ""): JsonRow[] => {
  if (Array.isArray(value)) {
    if (value.length === 0) {
      return [{ label: prefix || "Items", value: "None" }];
    }
    if (value.every(isPrimitive)) {
      return [{ label: prefix || "Items", value: value.map(formatPrimitive).join(", ") }];
    }
    return value.flatMap((item, index) => {
      const label = `${prefix ? `${prefix} / ` : ""}Item ${index + 1}`;
      if (isPrimitive(item)) {
        return [{ label, value: formatPrimitive(item) }];
      }
      return flattenRows(item, label);
    });
  }
  if (value && typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    if (!entries.length) {
      return [{ label: prefix || "Details", value: "None" }];
    }
    return entries.flatMap(([key, entryValue]) => {
      const label = prefix ? `${prefix} / ${formatLabel(key)}` : formatLabel(key);
      if (isPrimitive(entryValue)) {
        return [{ label, value: formatPrimitive(entryValue) }];
      }
      return flattenRows(entryValue, label);
    });
  }
  return [{ label: prefix || "Value", value: formatPrimitive(value) }];
};

const deriveSectionTitle = (value: unknown, index: number) => {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    const record = value as Record<string, unknown>;
    const candidates = ["name", "title", "label", "id", "type", "path"];
    for (const key of candidates) {
      const candidate = record[key];
      if (typeof candidate === "string" && candidate.trim()) {
        return candidate;
      }
      if (typeof candidate === "number") {
        return `${key}: ${candidate}`;
      }
    }
  }
  return `Item ${index + 1}`;
};

const jsonSections = computed<JsonSection[]>(() => {
  const value = jsonCandidate.value;
  if (value === null || value === undefined) {
    return [];
  }
  if (Array.isArray(value)) {
    const sections = value.map((entry, index) => {
      const title = deriveSectionTitle(entry, index);
      const rows = flattenRows(entry);
      return {
        key: `${index}-${title}`,
        title,
        meta: `${rows.length} fields`,
        rows,
        open: props.accordionOpenByDefault && index === 0
      };
    });
    const singleRow = sections.filter((section) => section.rows.length === 1);
    const multiRow = sections.filter((section) => section.rows.length > 1);
    if (singleRow.length) {
      const mergedRows = singleRow.map((section) => ({
        label: section.title,
        value: section.rows[0].value
      }));
      const summary = {
        key: "summary",
        title: "Details",
        meta: `${mergedRows.length} fields`,
        rows: mergedRows,
        open: props.accordionOpenByDefault
      };
      return multiRow.length ? [summary, ...multiRow] : [summary];
    }
    return sections;
  }
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    const sections: JsonSection[] = [];
    const mergedRows: JsonRow[] = [];
    entries.forEach(([key, entryValue], index) => {
      const title = formatLabel(key);
      const rows = flattenRows(entryValue);
      if (rows.length <= 1) {
        mergedRows.push(...flattenRows(entryValue, title));
      } else {
        sections.push({
          key,
          title,
          meta: `${rows.length} fields`,
          rows,
          open: props.accordionOpenByDefault && index === 0
        });
      }
    });
    if (mergedRows.length) {
      sections.unshift({
        key: "summary",
        title: "Details",
        meta: `${mergedRows.length} fields`,
        rows: mergedRows,
        open: props.accordionOpenByDefault
      });
    }
    return sections;
  }
  return [];
});

const showAccordion = computed(() => renderMode.value === "json" && jsonSections.value.length > 0);
</script>
