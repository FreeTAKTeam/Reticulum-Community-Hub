<template>
  <div class="event-feed">
    <div class="event-feed__header">
      <slot name="title" />
      <BaseInput
        id="event-feed-search"
        v-model="search"
        class="event-feed__search"
        type="search"
        placeholder="Search events, names, IDs"
        size="sm"
      />
    </div>

    <CosmicTabs v-model="category" :options="tabOptions" aria-label="Event categories" />

    <div class="event-feed__body cui-scrollbar">
      <p v-if="!pageGroups.length" class="event-feed__empty" role="status">{{ emptyText }}</p>
      <ol v-else class="event-feed__list">
        <template v-for="row in pageRows" :key="row.key">
          <li v-if="row.day" class="event-feed__day" role="presentation">
            <span>{{ row.day }}</span>
          </li>
          <li
            v-else-if="row.group"
            class="event-feed__item"
            :class="[`event-feed__item--${row.group.presented.category}`, { 'event-feed__item--open': isOpen(row.key) }]"
          >
            <div class="event-feed__row">
              <span class="event-feed__icon" aria-hidden="true">
                <svg viewBox="0 0 24 24"><path :d="CATEGORY_ICONS[row.group.presented.category]" /></svg>
              </span>
              <div class="event-feed__text">
                <span class="event-feed__title">
                  {{ row.group.presented.title }}<span v-if="row.group.events.length > 1" class="event-feed__count">
                    ×{{ row.group.events.length }}</span>
                </span>
                <span v-if="row.group.presented.summary" class="event-feed__summary">{{ row.group.presented.summary }}</span>
              </div>
              <div class="event-feed__time" :title="fullTime(row.group.events[0])">
                <span class="event-feed__clock">{{ clockTime(row.group.events[0]) }}</span>
                <span class="event-feed__ago">{{ relativeTime(row.group.events[0]) }}</span>
              </div>
              <button
                type="button"
                class="event-feed__toggle"
                :aria-expanded="isOpen(row.key)"
                :aria-label="isOpen(row.key) ? 'Hide details' : 'Show details'"
                @click="toggle(row.key)"
              >
                <svg viewBox="0 0 24 24" aria-hidden="true"><path :d="isOpen(row.key) ? 'M6 15l6-6 6 6' : 'M6 9l6 6 6-6'" /></svg>
              </button>
            </div>
            <div v-if="isOpen(row.key)" class="event-feed__details">
              <dl v-if="row.group.presented.details.length" class="event-feed__fields">
                <template v-for="(detail, index) in row.group.presented.details" :key="`${row.key}-d${index}`">
                  <dt>{{ detail.label }}</dt>
                  <dd>{{ detail.value }}<span v-if="detail.mono" class="event-feed__mono">{{ detail.mono }}</span></dd>
                </template>
              </dl>
              <p v-else class="event-feed__summary">No further details.</p>
              <ul v-if="row.group.events.length > 1" class="event-feed__occurrences">
                <li v-for="(event, index) in row.group.events.slice(0, 10)" :key="`${row.key}-o${index}`">
                  <span class="event-feed__mono">{{ clockTime(event) }}</span>
                  <span>{{ present(event).summary || present(event).title }}</span>
                </li>
              </ul>
              <div class="event-feed__links">
                <button type="button" class="event-feed__link" @click="toggleRaw(row.key)">
                  {{ rawOpen[row.key] ? "Hide raw data" : "Show raw data" }}
                </button>
                <button v-if="row.group.events[0].id" type="button" class="event-feed__link" @click="copyId(row.group.events[0])">
                  Copy event ID
                </button>
              </div>
              <BaseFormattedOutput v-if="rawOpen[row.key]" class="event-feed__raw" :value="row.group.events[0].metadata ?? {}" />
            </div>
          </li>
        </template>
      </ol>
    </div>

    <div class="event-feed__footer">
      <span v-if="hiddenTransportCount && !showTransport">
        {{ hiddenTransportCount }} transport {{ hiddenTransportCount === 1 ? "step" : "steps" }} hidden ·
        <button type="button" class="event-feed__link" @click="showTransport = true">Show transport internals</button>
      </span>
      <span v-else-if="showTransport">
        <button type="button" class="event-feed__link" @click="showTransport = false">Hide transport internals</button>
      </span>
      <span v-else></span>
      <BasePagination v-model:page="page" :page-size="PAGE_SIZE" :total="groups.length" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from "vue";
import BaseFormattedOutput from "../BaseFormattedOutput.vue";
import BaseInput from "../BaseInput.vue";
import BasePagination from "../BasePagination.vue";
import CosmicTabs from "../cosmic/CosmicTabs.vue";
import type { EventEntry, IdentityEntry } from "../../api/types";
import { useIdentityEnrichment } from "../../composables/useIdentityEnrichment";
import { eventEntryKey } from "../../stores/dashboard";
import { useToastStore } from "../../stores/toasts";
import { buildEventCallsignLookup, eventIdentityTokens } from "../../utils/event-feed";
import { presentEvent, type EventCategory, type PresentedEvent } from "../../utils/event-presentation";

const props = defineProps<{
  events: EventEntry[];
  /** Callsigns already known to the dashboard (team members, users). */
  identities: ReadonlyMap<string, string>;
  missions?: ReadonlyMap<string, string>;
}>();

const PAGE_SIZE = 12;
const GROUP_WINDOW_MS = 15 * 60 * 1000;

const CATEGORY_ICONS: Record<EventCategory, string> = {
  messages: "M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z",
  location: "M12 21s-7-6.2-7-11a7 7 0 0 1 14 0c0 4.8-7 11-7 11zM12 12.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5",
  map: "M3 6l6-3 6 3 6-3v15l-6 3-6-3-6 3zM9 3v15M15 6v15",
  missions: "M4 22V4M4 4h12l-2 4 2 4H4",
  users: "M16 21v-2a4 4 0 0 0-8 0v2M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8",
  system: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1",
  errors: "M12 9v4M12 17h.01M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z",
  transport: "M7 7h10l-3-3M17 17H7l3 3"
};

type Filter = "all" | Exclude<EventCategory, "transport">;
const TABS: Array<{ value: Filter; label: string }> = [
  { value: "all", label: "All" },
  { value: "messages", label: "Messages" },
  { value: "location", label: "Location" },
  { value: "map", label: "Map" },
  { value: "missions", label: "Missions" },
  { value: "users", label: "Users" },
  { value: "system", label: "System" },
  { value: "errors", label: "Errors" }
];

const toastStore = useToastStore();
const category = ref<Filter>("all");
const search = ref("");
const showTransport = ref(false);
const page = ref(1);
const openRows = reactive<Record<string, boolean>>({});
const rawOpen = reactive<Record<string, boolean>>({});

const now = ref(Date.now());
const clockTimer = window.setInterval(() => { now.value = Date.now(); }, 30_000);
onBeforeUnmount(() => window.clearInterval(clockTimer));

// Names: the dashboard's lookup plus identities enriched for the visible page.
const visibleEvents = ref<EventEntry[]>([]);
const directory = useIdentityEnrichment(computed(() => eventIdentityTokens(visibleEvents.value)));
const lookup = computed(() => {
  const merged = new Map(props.identities);
  const identities = [...directory.cache.values()].filter((entry): entry is IdentityEntry => entry !== null);
  const enriched = buildEventCallsignLookup({ identities });
  enriched.forEach((name, id) => { if (!merged.has(id)) merged.set(id, name); });
  directory.cache.forEach((entry, requestKey) => {
    const name = entry?.id ? enriched.get(entry.id.trim().toLowerCase()) : undefined;
    if (name && !merged.has(requestKey)) merged.set(requestKey, name);
  });
  return merged;
});

const presentedCache = computed(() => {
  const lookups = { identities: lookup.value, missions: props.missions };
  const cache = new Map<EventEntry, PresentedEvent>();
  props.events.forEach((event) => cache.set(event, presentEvent(event, lookups)));
  return cache;
});
const present = (event: EventEntry): PresentedEvent =>
  presentedCache.value.get(event) ?? presentEvent(event, { identities: lookup.value, missions: props.missions });

const eventTimeMs = (event: EventEntry) => {
  const parsed = Date.parse(event.created_at ?? "");
  return Number.isNaN(parsed) ? 0 : parsed;
};

const hiddenTransportCount = computed(() => props.events.filter((event) => present(event).transport).length);

const filtered = computed(() => {
  const term = search.value.trim().toLowerCase();
  return props.events.filter((event) => {
    const presented = present(event);
    if (presented.transport && !showTransport.value) return false;
    if (category.value !== "all" && presented.category !== category.value) return false;
    if (!term) return true;
    return [
      presented.title,
      presented.summary,
      event.category ?? "",
      event.message ?? "",
      ...presented.details.map((detail) => `${detail.value} ${detail.mono ?? ""}`)
    ].some((field) => field.toLowerCase().includes(term));
  });
});

interface EventGroup { key: string; events: EventEntry[]; presented: PresentedEvent }

// Consecutive events with the same title collapse into one row, e.g. "Location update ×3".
const groups = computed<EventGroup[]>(() => {
  const result: EventGroup[] = [];
  for (const event of filtered.value) {
    const presented = present(event);
    const last = result[result.length - 1];
    if (
      last &&
      last.presented.title === presented.title &&
      last.presented.category === presented.category &&
      eventTimeMs(last.events[last.events.length - 1]) - eventTimeMs(event) <= GROUP_WINDOW_MS
    ) {
      last.events.push(event);
      continue;
    }
    result.push({ key: eventEntryKey(event), events: [event], presented });
  }
  return result;
});

const pageCount = computed(() => Math.max(1, Math.ceil(groups.value.length / PAGE_SIZE)));
watch(pageCount, (count) => { if (page.value > count) page.value = count; });
watch([category, search, showTransport], () => { page.value = 1; });

const pageGroups = computed(() => groups.value.slice((page.value - 1) * PAGE_SIZE, page.value * PAGE_SIZE));
watch(pageGroups, (list) => { visibleEvents.value = list.flatMap((group) => group.events.slice(0, 10)); }, { immediate: true });

const dayKey = (ms: number) => new Date(ms).toDateString();
const dayLabel = (ms: number) => {
  if (!ms) return "Unknown date";
  const date = new Date(ms);
  const label = date.toLocaleDateString([], { weekday: "short", day: "numeric", month: "short" });
  const today = new Date(now.value);
  const yesterday = new Date(now.value - 86_400_000);
  if (dayKey(ms) === today.toDateString()) return `Today · ${label}`;
  if (dayKey(ms) === yesterday.toDateString()) return `Yesterday · ${label}`;
  return label;
};

const pageRows = computed(() => {
  const rows: Array<{ key: string; day?: string; group?: EventGroup }> = [];
  let previousDay = "";
  pageGroups.value.forEach((group) => {
    const ms = eventTimeMs(group.events[0]);
    const day = ms ? dayKey(ms) : "unknown";
    if (day !== previousDay) {
      rows.push({ key: `day-${day}-${group.key}`, day: dayLabel(ms) });
      previousDay = day;
    }
    rows.push({ key: group.key, group });
  });
  return rows;
});

const clockTime = (event: EventEntry) => {
  const ms = eventTimeMs(event);
  return ms ? new Date(ms).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "–";
};
const fullTime = (event: EventEntry) => {
  const ms = eventTimeMs(event);
  return ms ? new Date(ms).toLocaleString() : "";
};
const relativeTime = (event: EventEntry) => {
  const ms = eventTimeMs(event);
  if (!ms) return "";
  const minutes = Math.round((now.value - ms) / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  return days === 1 ? "yesterday" : `${days} days ago`;
};

const isOpen = (key: string) => Boolean(openRows[key]);
const toggle = (key: string) => { openRows[key] = !openRows[key]; };
const toggleRaw = (key: string) => { rawOpen[key] = !rawOpen[key]; };

const copyId = async (event: EventEntry) => {
  try {
    await navigator.clipboard.writeText(event.id ?? "");
    toastStore.push("Event ID copied", "success");
  } catch (error) {
    console.warn("Unable to copy event ID", error);
    toastStore.push("Unable to copy event ID", "warning");
  }
};

const tabOptions = TABS;
const emptyText = computed(() => {
  if (!props.events.length) return "No events yet.";
  if (search.value.trim()) return "No events match this search.";
  return "No events in this category.";
});
</script>

<style scoped>
.event-feed {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 0;
  height: 100%;
  font-family: var(--cui-font-body);
  color: var(--cui-color-text);
}

.event-feed__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.event-feed__search {
  width: min(260px, 100%);
}

.event-feed__search :deep(.cui-field__label-row) {
  display: none;
}

.event-feed__body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding-right: 2px;
}

.event-feed__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.event-feed__day {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 2px 2px;
  font-size: 0.7rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--cui-color-text-muted);
}

.event-feed__day::after {
  content: "";
  flex: 1;
  height: 1px;
  background: var(--cui-color-border-soft);
}

.event-feed__item {
  --tone: var(--cui-color-tone-primary);
  border: 1px solid var(--cui-color-border-soft);
  border-radius: var(--cui-radius-md);
  background: var(--cui-color-panel-1);
}

.event-feed__item--messages { --tone: var(--cui-color-tone-primary); }
.event-feed__item--location { --tone: var(--cui-color-tone-success); }
.event-feed__item--map { --tone: var(--cui-color-tone-warning); }
.event-feed__item--missions { --tone: var(--cui-accent-warm); }
.event-feed__item--users { --tone: var(--cui-color-tone-info); }
.event-feed__item--system { --tone: var(--cui-color-tone-neutral); }
.event-feed__item--transport { --tone: var(--cui-color-tone-secondary); }

.event-feed__item--errors {
  --tone: var(--cui-color-tone-danger);
  border-color: rgba(255, 59, 122, 0.45);
  background: rgba(255, 59, 122, 0.08);
}

.event-feed__item--open {
  border-color: color-mix(in srgb, var(--tone) 50%, transparent);
}

.event-feed__row {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr) auto 32px;
  align-items: center;
  gap: 12px;
  padding: 8px 10px;
}

.event-feed__icon {
  width: 34px;
  height: 34px;
  border-radius: 9px;
  display: grid;
  place-items: center;
  color: var(--tone);
  background: color-mix(in srgb, var(--tone) 14%, transparent);
}

.event-feed__icon svg,
.event-feed__toggle svg {
  width: 18px;
  height: 18px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.event-feed__text {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.event-feed__title {
  font-size: 1rem;
  font-weight: 400;
  color: var(--cui-color-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.event-feed__count {
  color: var(--tone);
}

.event-feed__summary {
  margin: 0;
  font-size: 0.85rem;
  color: var(--cui-color-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.event-feed__time {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 1px;
}

.event-feed__clock {
  font-family: var(--cui-font-mono);
  font-size: 0.75rem;
  color: var(--cui-color-text);
}

.event-feed__ago {
  font-size: 0.7rem;
  letter-spacing: 0.08em;
  color: var(--cui-color-text-muted);
}

.event-feed__toggle {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  border: 1px solid var(--cui-color-border);
  background: transparent;
  color: var(--cui-color-tone-primary);
  display: grid;
  place-items: center;
  cursor: pointer;
}

.event-feed__toggle svg {
  width: 14px;
  height: 14px;
  stroke-width: 2.4;
}

.event-feed__toggle:focus-visible,
.event-feed__link:focus-visible {
  outline: 2px solid var(--cui-color-tone-primary);
  outline-offset: 2px;
}

.event-feed__details {
  margin: 0 10px 10px 56px;
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--cui-color-bg-0);
  border: 1px solid var(--cui-color-border-soft);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.event-feed__fields {
  margin: 0;
  display: grid;
  grid-template-columns: minmax(90px, 140px) minmax(0, 1fr);
  gap: 6px 14px;
  align-items: baseline;
  font-size: 0.85rem;
}

.event-feed__fields dt {
  font-size: 0.7rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--cui-color-text-muted);
}

.event-feed__fields dd {
  margin: 0;
  overflow-wrap: anywhere;
}

.event-feed__mono {
  font-family: var(--cui-font-mono);
  font-size: 0.75rem;
  color: var(--cui-color-text-muted);
}

.event-feed__occurrences {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 0.85rem;
  color: var(--cui-color-text-muted);
}

.event-feed__occurrences li {
  display: flex;
  gap: 10px;
}

.event-feed__links {
  display: flex;
  gap: 14px;
  font-size: 0.85rem;
}

.event-feed__link {
  padding: 0;
  border: 0;
  background: none;
  color: var(--cui-color-tone-primary);
  font: inherit;
  cursor: pointer;
}

.event-feed__link:hover {
  color: var(--cui-color-tone-info);
  text-decoration: underline;
}

.event-feed__raw {
  max-height: 220px;
  overflow: auto;
}

.event-feed__empty {
  margin: 12px 0;
  font-size: 0.85rem;
  color: var(--cui-color-text-muted);
}

.event-feed__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  padding-top: 6px;
  border-top: 1px solid var(--cui-color-border-soft);
  font-size: 0.85rem;
  color: var(--cui-color-text-muted);
}

@media (max-width: 640px) {
  .event-feed__row {
    grid-template-columns: 30px minmax(0, 1fr) 32px;
  }

  .event-feed__time {
    grid-column: 2;
    grid-row: 2;
    flex-direction: row;
    align-items: baseline;
    gap: 8px;
  }

  .event-feed__details {
    margin-left: 10px;
  }
}
</style>
