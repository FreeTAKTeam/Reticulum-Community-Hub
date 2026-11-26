<script setup lang="ts">
import type { GeoJSONSource, Map as MapLibreMap, MapGeoJSONFeature } from "maplibre-gl";
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { del } from "../../api/client";
import { endpoints } from "../../api/endpoints";
import { useMarkersStore } from "../../stores/markers";
import { useToastStore } from "../../stores/toasts";
import BaseButton from "../BaseButton.vue";

// Shift+drag selects every marker and event in a box; Shift+click adds or removes one.
const props = defineProps<{ map: MapLibreMap | null }>();
const emit = defineEmits<{ (event: "deleted", value: { markers: number; events: number }): void }>();

type Kind = "marker" | "event";
interface Picked { kind: Kind; id: string; lon: number; lat: number }

const MARKER_LAYER = "operator-marker-layer";
const EVENT_LAYER = "rch-events-point";
const SOURCE = "map-selection";
const LAYER = "map-selection-ring";
// Below this drag distance (px) the gesture is a Shift+click on one item.
const CLICK_SLOP = 4;
const CLICK_PAD = 8;

const markersStore = useMarkersStore();
const toastStore = useToastStore();
const selected = ref<Map<string, Picked>>(new Map());
const box = ref<{ x: number; y: number; w: number; h: number } | null>(null);
const deleting = ref(false);
let start: { x: number; y: number } | null = null;

const counts = computed(() => {
  const items = [...selected.value.values()];
  return { markers: items.filter((item) => item.kind === "marker").length, events: items.filter((item) => item.kind === "event").length };
});
const summary = computed(() => {
  const parts = [];
  if (counts.value.markers) parts.push(`${counts.value.markers} marker${counts.value.markers === 1 ? "" : "s"}`);
  if (counts.value.events) parts.push(`${counts.value.events} event${counts.value.events === 1 ? "" : "s"}`);
  return parts.join(", ");
});

const pick = (feature: MapGeoJSONFeature): Picked | null => {
  const kind: Kind = feature.layer.id === EVENT_LAYER ? "event" : "marker";
  const id = String(feature.properties?.[kind === "event" ? "uid" : "id"] ?? "");
  const [lon, lat] = (feature.geometry as GeoJSON.Point).coordinates ?? [];
  return id && typeof lon === "number" && typeof lat === "number" ? { kind, id, lon, lat } : null;
};

function draw(): void {
  const map = props.map;
  if (!map) return;
  const data: GeoJSON.FeatureCollection = {
    type: "FeatureCollection",
    features: [...selected.value.values()].map((item) => ({
      type: "Feature", properties: {}, geometry: { type: "Point", coordinates: [item.lon, item.lat] }
    }))
  };
  try {
    const source = map.getSource(SOURCE) as GeoJSONSource | undefined;
    if (source) {
      source.setData(data);
    } else {
      map.addSource(SOURCE, { type: "geojson", data });
      map.addLayer({ id: LAYER, source: SOURCE, type: "circle", paint: {
        "circle-radius": 22,
        "circle-color": "rgba(55, 242, 255, 0.12)",
        "circle-stroke-color": "#37f2ff",
        "circle-stroke-width": 2
      } });
    }
  } catch (error) {
    // The style may still be loading; the next styledata redraws.
    console.warn("[map] selection could not be drawn", error);
  }
}

function clear(): void {
  selected.value = new Map();
  draw();
}

const local = (event: MouseEvent) => {
  const rect = props.map!.getCanvas().getBoundingClientRect();
  return { x: event.clientX - rect.left, y: event.clientY - rect.top };
};

function onMouseDown(event: MouseEvent): void {
  if (!event.shiftKey || event.button !== 0 || !props.map) return;
  // Keep MapLibre's box zoom, map pan and marker drag from seeing this gesture.
  event.preventDefault();
  event.stopPropagation();
  start = local(event);
  box.value = { ...start, w: 0, h: 0 };
  window.addEventListener("mousemove", onMouseMove);
  window.addEventListener("mouseup", onMouseUp, { once: true });
}

function onMouseMove(event: MouseEvent): void {
  if (!start) return;
  const point = local(event);
  box.value = { x: Math.min(start.x, point.x), y: Math.min(start.y, point.y), w: Math.abs(point.x - start.x), h: Math.abs(point.y - start.y) };
}

function onMouseUp(): void {
  window.removeEventListener("mousemove", onMouseMove);
  const map = props.map;
  const area = box.value;
  start = null;
  box.value = null;
  if (!map || !area) return;
  const isClick = area.w < CLICK_SLOP && area.h < CLICK_SLOP;
  const bounds: [[number, number], [number, number]] = isClick
    ? [[area.x - CLICK_PAD, area.y - CLICK_PAD], [area.x + CLICK_PAD, area.y + CLICK_PAD]]
    : [[area.x, area.y], [area.x + area.w, area.y + area.h]];
  const layers = [MARKER_LAYER, EVENT_LAYER].filter((layer) => map.getLayer(layer));
  if (!layers.length) return;
  const hits = map.queryRenderedFeatures(bounds, { layers }).map(pick).filter((item): item is Picked => item !== null);
  const next = new Map(selected.value);
  if (isClick) {
    const hit = hits[0];
    if (!hit) return;
    const key = `${hit.kind}:${hit.id}`;
    if (next.has(key)) next.delete(key); else next.set(key, hit);
  } else {
    for (const hit of hits) next.set(`${hit.kind}:${hit.id}`, hit);
  }
  selected.value = next;
  draw();
}

// A Shift+click would otherwise also open the event window or place a marker.
function onClick(event: MouseEvent): void {
  if (event.shiftKey) event.stopPropagation();
}

function onKeyDown(event: KeyboardEvent): void {
  if (event.key === "Escape" && selected.value.size) clear();
}

async function deleteSelected(): Promise<void> {
  const items = [...selected.value.values()];
  if (!items.length || !window.confirm(`Delete ${summary.value}? Events are also removed from their mission log.`)) return;
  deleting.value = true;
  const results = await Promise.allSettled(items.map((item) =>
    item.kind === "marker"
      ? markersStore.deleteMarker(item.id)
      : del(`${endpoints.r3aktLogEntries}/${encodeURIComponent(item.id)}`)
  ));
  deleting.value = false;
  const failed = new Map(items.filter((_, index) => results[index].status === "rejected").map((item) => [`${item.kind}:${item.id}`, item]));
  const done = items.filter((item) => !failed.has(`${item.kind}:${item.id}`));
  emit("deleted", { markers: done.filter((item) => item.kind === "marker").length, events: done.filter((item) => item.kind === "event").length });
  // Keep what failed selected so it can be retried.
  selected.value = failed;
  draw();
  if (failed.size) toastStore.push(`Deleted ${done.length}; ${failed.size} could not be deleted`, "danger");
  else toastStore.push(`Deleted ${done.length} item${done.length === 1 ? "" : "s"}`, "warning");
}

// MapLibre's own mouse handlers sit on the canvas container; a capture listener there runs first.
const surface = (map: MapLibreMap | null) => map?.getCanvas?.()?.parentElement ?? null;
function attach(map: MapLibreMap | null): void {
  surface(map)?.addEventListener("mousedown", onMouseDown, true);
  surface(map)?.addEventListener("click", onClick, true);
  map?.on("styledata", draw);
}
function detach(map: MapLibreMap | null): void {
  surface(map)?.removeEventListener("mousedown", onMouseDown, true);
  surface(map)?.removeEventListener("click", onClick, true);
  map?.off("styledata", draw);
}

watch(() => props.map, (map, previous) => { detach(previous ?? null); attach(map); }, { immediate: true });
window.addEventListener("keydown", onKeyDown);
onBeforeUnmount(() => {
  detach(props.map);
  window.removeEventListener("keydown", onKeyDown);
  window.removeEventListener("mousemove", onMouseMove);
  window.removeEventListener("mouseup", onMouseUp);
});
defineExpose({ selected });
</script>

<template>
  <div
    v-if="box"
    class="map-selection-box"
    :style="{ left: `${box.x}px`, top: `${box.y}px`, width: `${box.w}px`, height: `${box.h}px` }"
    aria-hidden="true"
  />
  <div v-if="selected.size" class="map-selection-bar" role="toolbar" aria-label="Map selection">
    <span class="map-selection-count">{{ summary }} selected</span>
    <BaseButton size="sm" variant="danger" icon-left="trash" :disabled="deleting" @click="deleteSelected">Delete</BaseButton>
    <BaseButton size="sm" variant="secondary" :disabled="deleting" @click="clear">Clear</BaseButton>
    <span class="map-selection-hint">Shift+drag to add · Shift+click to toggle · Esc to clear</span>
  </div>
</template>

<style scoped>
.map-selection-box {
  position: absolute;
  z-index: 5;
  border: 1px dashed #37f2ff;
  background: rgba(55, 242, 255, 0.1);
  pointer-events: none;
}

.map-selection-bar {
  position: absolute;
  top: 16px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 6;
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  padding: 8px 12px;
  border: 1px solid rgba(55, 242, 255, 0.35);
  border-radius: 12px;
  background: rgba(6, 18, 28, 0.92);
  color: var(--cui-color-text);
  font-family: var(--cui-font-body);
}

.map-selection-count {
  font-size: 0.85rem;
  letter-spacing: 0.06em;
}

.map-selection-hint {
  font-size: 0.72rem;
  color: var(--cui-color-text-muted);
}
</style>
