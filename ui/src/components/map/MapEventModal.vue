<template>
  <BaseModal :open="true" :title="title" size="lg" @close="emit('close')">
    <template #header="{ titleId }">
      <div class="map-event-heading">
        <h3 :id="titleId" class="text-lg font-semibold">{{ title }}</h3>
        <span v-if="event.severity" class="map-event-severity" :class="`map-event-severity--${event.severity.key}`">
          {{ event.severity.label }}
        </span>
      </div>
    </template>

    <div class="map-event-grid">
      <section class="map-event-card" aria-labelledby="map-event-report">
        <div class="map-event-card-head">
          <h4 id="map-event-report" class="map-event-card-title">Report</h4>
          <p class="map-event-card-desc">What the sender reported.</p>
        </div>
        <p class="map-event-headline">{{ event.headline || "No text" }}</p>
        <dl class="map-event-fields">
          <template v-if="event.severity">
            <dt>Severity</dt>
            <dd>{{ event.severity.label }}</dd>
          </template>
          <dt>Category</dt>
          <dd>{{ event.rawCode ? event.categoryLabel : "Log entry (no MECP code)" }}</dd>
          <template v-if="event.rawCode">
            <dt>MECP code</dt>
            <dd class="map-event-mono">{{ event.rawCode }}</dd>
          </template>
          <template v-if="event.warnings.length">
            <dt>Warnings</dt>
            <dd>{{ event.warnings.join(" · ") }}</dd>
          </template>
        </dl>
      </section>

      <section class="map-event-card" aria-labelledby="map-event-location">
        <div class="map-event-card-head">
          <h4 id="map-event-location" class="map-event-card-title">Location</h4>
          <p class="map-event-card-desc">Where the event was reported.</p>
        </div>
        <dl class="map-event-fields">
          <dt>Coordinates</dt>
          <dd class="map-event-mono">{{ coordinates }}</dd>
          <dt>Source</dt>
          <dd>{{ event.locationSource }}</dd>
        </dl>
        <div class="map-event-actions">
          <BaseButton variant="secondary" icon-left="route" @click="emit('center', event)">Center map</BaseButton>
          <BaseButton variant="secondary" icon-left="file" @click="copyCoordinates">Copy</BaseButton>
        </div>
      </section>

      <section class="map-event-card" aria-labelledby="map-event-sender">
        <div class="map-event-card-head">
          <h4 id="map-event-sender" class="map-event-card-title">Sender</h4>
          <p class="map-event-card-desc">Who sent it and when.</p>
        </div>
        <dl class="map-event-fields">
          <dt>Callsign</dt>
          <dd>{{ event.callsign || "Unknown" }}</dd>
          <template v-if="event.reportedAt">
            <dt>Reported</dt>
            <dd>{{ formatTime(event.reportedAt) }}</dd>
          </template>
          <dt>Received</dt>
          <dd>{{ formatTime(event.receivedAt) }}<span v-if="receivedAgo" class="map-event-muted"> · {{ receivedAgo }}</span></dd>
        </dl>
      </section>

      <section class="map-event-card" aria-labelledby="map-event-mission">
        <div class="map-event-card-head">
          <h4 id="map-event-mission" class="map-event-card-title">Mission</h4>
          <p class="map-event-card-desc">The mission log this event belongs to.</p>
        </div>
        <dl class="map-event-fields">
          <dt>Mission</dt>
          <dd>{{ missionName || event.missionUid || "None" }}</dd>
          <template v-if="event.extras.length">
            <dt>Extras</dt>
            <dd>{{ event.extras.join(" · ") }}</dd>
          </template>
        </dl>
        <div v-if="event.keywords.length" class="map-event-keywords">
          <span v-for="keyword in event.keywords" :key="keyword" class="map-event-keyword">{{ keyword }}</span>
        </div>
        <div v-if="event.missionUid" class="map-event-actions">
          <BaseButton variant="secondary" icon-left="list" @click="emit('open-mission-log', event.missionUid)">
            Open mission log
          </BaseButton>
        </div>
      </section>
    </div>
  </BaseModal>
</template>

<script setup lang="ts">
import { computed } from "vue";
import BaseButton from "../BaseButton.vue";
import BaseModal from "../BaseModal.vue";
import { useToastStore } from "../../stores/toasts";
import type { MapEventView } from "../../utils/event-map";

const props = defineProps<{ event: MapEventView; missionName?: string; now?: number }>();
const emit = defineEmits<{
  (event: "close"): void;
  (event: "center", value: MapEventView): void;
  (event: "open-mission-log", missionUid: string): void;
}>();

const toastStore = useToastStore();
const title = computed(() => `Map Event: ${props.event.categoryLabel}`);
const coordinates = computed(() => `${props.event.lat.toFixed(6)}, ${props.event.lon.toFixed(6)}`);

const formatTime = (value: string) => {
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? value || "–" : new Date(parsed).toLocaleString();
};

const receivedAgo = computed(() => {
  const parsed = Date.parse(props.event.receivedAt);
  if (Number.isNaN(parsed)) return "";
  const minutes = Math.round(((props.now ?? Date.now()) - parsed) / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  return hours < 24 ? `${hours} h ago` : `${Math.round(hours / 24)} days ago`;
});

const copyCoordinates = async () => {
  try {
    await navigator.clipboard.writeText(coordinates.value);
    toastStore.push("Coordinates copied", "success");
  } catch (error) {
    console.warn("Unable to copy coordinates", error);
    toastStore.push("Unable to copy coordinates", "warning");
  }
};
</script>

<style scoped>
/* Section cards follow the Topic Assets dialog (TopicsPage .topic-assets-*). */
.map-event-heading {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.map-event-severity {
  --tone: var(--cui-color-tone-neutral);
  padding: 2px 10px;
  border-radius: 999px;
  border: 1px solid var(--tone);
  background: color-mix(in srgb, var(--tone) 16%, transparent);
  color: var(--cui-color-text);
  font-size: 0.7rem;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.map-event-severity--mayday { --tone: var(--cui-color-tone-danger); }
.map-event-severity--urgent { --tone: var(--cui-color-tone-warning); }
.map-event-severity--safety { --tone: var(--cui-color-tone-success); }
.map-event-severity--routine { --tone: var(--cui-color-tone-primary); }

.map-event-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.map-event-card {
  border: 1px solid rgba(55, 242, 255, 0.18);
  border-radius: 12px;
  background: rgba(6, 18, 28, 0.72);
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
}

.map-event-card-head {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.map-event-card-title {
  margin: 0;
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: rgba(217, 251, 255, 0.86);
}

.map-event-card-desc {
  margin: 0;
  font-family: "Rajdhani", "Barlow", sans-serif;
  font-size: 12px;
  line-height: 1.4;
  color: rgba(210, 251, 255, 0.72);
}

.map-event-headline {
  margin: 0;
  font-size: 1rem;
  color: var(--cui-color-text);
  overflow-wrap: anywhere;
}

.map-event-fields {
  margin: 0;
  display: grid;
  grid-template-columns: 110px minmax(0, 1fr);
  gap: 7px 12px;
  align-items: baseline;
}

.map-event-fields dt {
  font-size: 0.7rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--cui-color-text-muted);
}

.map-event-fields dd {
  margin: 0;
  font-size: 0.85rem;
  color: var(--cui-color-text);
  overflow-wrap: anywhere;
}

.map-event-mono,
.map-event-fields dd.map-event-mono {
  font-family: var(--cui-font-mono);
  font-size: 0.75rem;
}

.map-event-muted {
  color: var(--cui-color-text-muted);
}

.map-event-keywords {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.map-event-keyword {
  padding: 1px 8px;
  border: 1px solid var(--cui-color-border);
  font-size: 0.7rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--cui-color-text-muted);
}

.map-event-actions {
  margin-top: auto;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}

@media (max-width: 640px) {
  .map-event-grid {
    grid-template-columns: 1fr;
  }
}
</style>
