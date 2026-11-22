<script setup lang="ts">
import * as maplibregl from "maplibre-gl";
import type { Map as MapLibreMap, GeoJSONSource, MapLayerMouseEvent } from "maplibre-gl";
import { onBeforeUnmount, onMounted, watch } from "vue";
import { get } from "../../api/client";
import { endpoints } from "../../api/endpoints";
import { eventFeatures } from "../../utils/event-map";

// Events (log entries with a position) get their own layer, apart from people and markers.
const props = defineProps<{ map: MapLibreMap | null }>();
const SOURCE = "rch-events";
const LAYER = "rch-events-point";
let data = eventFeatures([]);
let timer: ReturnType<typeof setInterval> | undefined;

function remove(map: MapLibreMap | null): void {
  if (!map) return;
  map.off("click", LAYER, showPopup);
  if (map.getLayer(LAYER)) map.removeLayer(LAYER);
  if (map.getSource(SOURCE)) map.removeSource(SOURCE);
}
function render(): void {
  const map = props.map;
  if (!map?.isStyleLoaded()) return;
  const source = map.getSource(SOURCE) as GeoJSONSource | undefined;
  if (source) {
    source.setData(data);
    return;
  }
  map.addSource(SOURCE, { type: "geojson", data });
  map.addLayer({ id: LAYER, source: SOURCE, type: "circle", paint: {
    "circle-radius": 8,
    "circle-color": ["match", ["get", "severity"], "red", "#e5484d", "yellow", "#f5c542", "green", "#3fb950", "blue", "#4c8dff", "#b48cff"],
    "circle-stroke-color": "#ffffff",
    "circle-stroke-width": 2
  } });
  map.on("click", LAYER, showPopup);
}
function showPopup(event: MapLayerMouseEvent): void {
  const feature = event.features?.[0];
  if (!feature || feature.geometry.type !== "Point" || !props.map) return;
  const p = feature.properties ?? {};
  const body = document.createElement("div");
  const title = document.createElement("strong");
  title.textContent = `${p.category}${p.callsign ? ` · ${p.callsign}` : ""}`;
  const text = document.createElement("p");
  text.textContent = String(p.content ?? "");
  body.append(title, text);
  new maplibregl.Popup().setLngLat(feature.geometry.coordinates as [number, number]).setDOMContent(body).addTo(props.map);
}
async function refresh(): Promise<void> {
  try {
    // The endpoint returns a bare array of log entries.
    const entries = await get<unknown>(endpoints.r3aktLogEntries);
    data = eventFeatures(Array.isArray(entries) ? entries : []);
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
onBeforeUnmount(() => { clearInterval(timer); props.map?.off("styledata", render); remove(props.map); });
</script>

<template><span hidden /></template>
