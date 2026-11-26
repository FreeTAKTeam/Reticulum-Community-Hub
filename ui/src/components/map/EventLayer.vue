<script setup lang="ts">
import type { Map as MapLibreMap, GeoJSONSource, MapLayerMouseEvent } from "maplibre-gl";
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { del, get } from "../../api/client";
import { endpoints } from "../../api/endpoints";
import { MISSION_DOMAIN_ROUTE_NAMES } from "../../types/missions/routes";
import {
  MAP_EVENT_SEVERITIES,
  eventFeatures,
  presentMapEvent,
  type MapEventSeverity,
  type MapEventView
} from "../../utils/event-map";
import { EVENT_ICON_PIXEL_RATIO, EVENT_SEVERITY_COLORS as SEVERITY_COLORS, drawEventIcon } from "../../utils/mecp-category-icons";
import { useToastStore } from "../../stores/toasts";
import MapEventModal from "./MapEventModal.vue";

// Events (log entries with a position) get their own layer, apart from people and markers.
const props = defineProps<{ map: MapLibreMap | null }>();
const SOURCE = "rch-events";
const LAYER = "rch-events-point";
const SELECTED_LAYER = "rch-events-selected";
// Street level, past marker clustering, so the event is shown on its own.
const FOCUS_ZOOM = 16;

const router = useRouter();
let entries: unknown[] = [];
let data = eventFeatures([]);
let dataChanged = true;
let lastSource: GeoJSONSource | undefined;
let timer: ReturnType<typeof setInterval> | undefined;
const selected = ref<MapEventView | null>(null);
const missionNames = ref<Map<string, string>>(new Map());
const present = ref<Set<MapEventSeverity>>(new Set());

const colorExpression = [
  "match",
  ["get", "severity"],
  ...MAP_EVENT_SEVERITIES.flatMap(({ key }) => [key, SEVERITY_COLORS[key]]),
  SEVERITY_COLORS.none
];
const legend = computed(() => MAP_EVENT_SEVERITIES.filter(({ key }) => present.value.has(key)));

function remove(map: MapLibreMap | null): void {
  if (!map) return;
  map.off("click", LAYER, select);
  map.off("mouseenter", LAYER, pointer);
  map.off("mouseleave", LAYER, unpointer);
  if (map.getLayer(SELECTED_LAYER)) map.removeLayer(SELECTED_LAYER);
  if (map.getLayer(LAYER)) map.removeLayer(LAYER);
  if (map.getSource(SOURCE)) map.removeSource(SOURCE);
}
function selectedFilter(): unknown[] {
  return ["==", ["get", "uid"], selected.value?.uid ?? ""];
}
let retryScheduled = false;
// isStyleLoaded() stays false while icons and glyphs load, so gating on it could
// skip the layer for good. Add it as soon as MapLibre accepts it; if the style is
// still being set up, try again once the map is idle.
function render(): void {
  const map = props.map;
  if (!map) return;
  try {
    addOrUpdate(map);
  } catch (error) {
    // MapLibre throws this while a style is still being set up; anything else is a real failure.
    if (!(error instanceof Error) || !error.message.includes("Style is not done loading")) {
      console.warn("[map] event layer could not be drawn", error);
      return;
    }
    if (retryScheduled) return;
    retryScheduled = true;
    map.once("idle", () => {
      retryScheduled = false;
      render();
    });
  }
}
// Events stay above zones and markers added later, so a Mayday is never hidden.
function keepOnTop(map: MapLibreMap): void {
  const layers = map.getStyle()?.layers ?? [];
  if (layers[layers.length - 1]?.id === LAYER || !map.getLayer(LAYER)) return;
  map.moveLayer(SELECTED_LAYER);
  map.moveLayer(LAYER);
}
// Style changes drop images, so this runs on every render; hasImage keeps it cheap.
function addIcons(map: MapLibreMap): void {
  for (const feature of data.features) {
    const id = String(feature.properties?.icon ?? "");
    if (!id || map.hasImage(id)) continue;
    const image = drawEventIcon(id);
    if (image) map.addImage(id, image, { pixelRatio: EVENT_ICON_PIXEL_RATIO });
  }
}
function addOrUpdate(map: MapLibreMap): void {
  addIcons(map);
  const source = map.getSource(SOURCE) as GeoJSONSource | undefined;
  if (source) {
    if (source !== lastSource || dataChanged) {
      source.setData(data);
      lastSource = source;
      dataChanged = false;
    }
    keepOnTop(map);
    return;
  }
  map.addSource(SOURCE, { type: "geojson", data });
  // Ring drawn under the selected event.
  map.addLayer({ id: SELECTED_LAYER, source: SOURCE, type: "circle", filter: selectedFilter() as never, paint: {
    "circle-radius": 24,
    "circle-color": "rgba(0, 0, 0, 0)",
    "circle-stroke-color": colorExpression as never,
    "circle-stroke-width": 3,
    "circle-stroke-opacity": 0.6
  } });
  map.addLayer({ id: LAYER, source: SOURCE, type: "symbol", layout: {
    "icon-image": ["get", "icon"],
    "icon-allow-overlap": true,
    "icon-ignore-placement": true
  } });
  map.on("click", LAYER, select);
  map.on("mouseenter", LAYER, pointer);
  map.on("mouseleave", LAYER, unpointer);
}
function pointer(): void {
  if (props.map) props.map.getCanvas().style.cursor = "pointer";
}
function unpointer(): void {
  if (props.map) props.map.getCanvas().style.cursor = "";
}
function highlight(): void {
  const map = props.map;
  if (map?.getLayer(SELECTED_LAYER)) map.setFilter(SELECTED_LAYER, selectedFilter() as never);
}
function select(event: MapLayerMouseEvent): void {
  const uid = String(event.features?.[0]?.properties?.uid ?? "");
  const entry = entries.find((item) => (item as { entry_uid?: unknown })?.entry_uid === uid);
  const view = presentMapEvent(entry);
  if (!view) return;
  selected.value = view;
  highlight();
  void loadMissionNames();
}
function close(): void {
  selected.value = null;
  highlight();
}
function center(view: MapEventView): void {
  const map = props.map;
  close();
  map?.flyTo({ center: [view.lon, view.lat], zoom: Math.max(map.getZoom(), FOCUS_ZOOM) });
}
function openMissionLog(view: MapEventView): void {
  close();
  void router?.push({
    name: MISSION_DOMAIN_ROUTE_NAMES.logEntry,
    params: { mission_uid: view.missionUid },
    query: { entry: view.uid }
  });
}
async function deleteEvent(view: MapEventView): Promise<void> {
  const toastStore = useToastStore();
  if (!window.confirm(`Delete the event "${view.headline || view.categoryLabel}"? It is removed from the mission log.`)) return;
  try {
    await del(`${endpoints.r3aktLogEntries}/${encodeURIComponent(view.uid)}`);
    toastStore.push("Event deleted", "warning");
    close();
    await refresh();
  } catch (error) {
    console.warn("[map] event delete failed", error);
    toastStore.push("Unable to delete event", "danger");
  }
}
let missionsRequested = false;
async function loadMissionNames(): Promise<void> {
  if (missionsRequested) return;
  missionsRequested = true;
  try {
    const missions = await get<unknown>(endpoints.r3aktMissions);
    const list = Array.isArray(missions) ? missions : [];
    missionNames.value = new Map(
      list
        .map((mission) => mission as { uid?: unknown; mission_name?: unknown })
        .filter((mission) => typeof mission.uid === "string" && typeof mission.mission_name === "string")
        .map((mission) => [String(mission.uid), String(mission.mission_name)])
    );
  } catch (error) {
    missionsRequested = false;
    console.warn("[map] mission names for the event window failed to load", error);
  }
}
async function refresh(): Promise<void> {
  try {
    // The endpoint returns a bare array of log entries.
    const response = await get<unknown>(endpoints.r3aktLogEntries);
    entries = Array.isArray(response) ? response : [];
    data = eventFeatures(entries);
    dataChanged = true;
    present.value = new Set(data.features.map((feature) => feature.properties?.severity as MapEventSeverity));
    render();
  } catch (error) {
    console.warn("[map] event layer refresh failed", error);
  }
}
watch(() => props.map, (map, previous) => {
  previous?.off("styledata", render);
  remove(previous);
  map?.on("styledata", render);
  render();
});
onMounted(() => {
  void refresh();
  timer = setInterval(() => { void refresh(); }, 10_000);
});
defineExpose({ refresh });
onBeforeUnmount(() => { clearInterval(timer); props.map?.off("styledata", render); remove(props.map); });
</script>

<template>
  <div v-if="legend.length" class="map-event-legend" aria-label="Map events">
    <span class="map-event-legend-title">Events</span>
    <span v-for="item in legend" :key="item.key" class="map-event-legend-item">
      <span class="map-event-legend-dot" :style="{ background: SEVERITY_COLORS[item.key] }" aria-hidden="true" />
      {{ item.label }}
    </span>
  </div>
  <MapEventModal
    v-if="selected"
    :event="selected"
    :mission-name="missionNames.get(selected.missionUid)"
    @close="close"
    @center="center"
    @open-mission-log="openMissionLog"
    @delete="deleteEvent"
  />
</template>

<style scoped>
.map-event-legend {
  position: absolute;
  right: 72px;
  bottom: 40px;
  z-index: 4;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 12px;
  border: 1px solid rgba(55, 242, 255, 0.18);
  border-radius: 12px;
  background: rgba(6, 18, 28, 0.85);
  font-family: var(--cui-font-body);
  color: var(--cui-color-text);
  pointer-events: none;
}

.map-event-legend-title {
  font-size: 11px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: rgba(217, 251, 255, 0.86);
}

.map-event-legend-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.8rem;
}

/* Square, like the event badges on the map. */
.map-event-legend-dot {
  width: 12px;
  height: 12px;
  border-radius: 3px;
}
</style>
