<script setup lang="ts">
import type { Map as MapLibreMap, GeoJSONSource } from "maplibre-gl";
import type { FeatureCollection } from "geojson";
import { onBeforeUnmount, onMounted, watch } from "vue";
import { useSensorsStore } from "../../stores/sensors";

const props = defineProps<{ map: MapLibreMap | null }>();
const store = useSensorsStore();
const SOURCE = "r3s-sensor-geometry";
const LAYERS = ["r3s-sensor-sector", "r3s-sensor-direction", "r3s-sensor-heading"];
let timer: ReturnType<typeof setInterval> | undefined;
function remove(map: MapLibreMap | null): void {
  if (!map) return;
  for (const id of LAYERS) if (map.getLayer(id)) map.removeLayer(id);
  if (map.getSource(SOURCE)) map.removeSource(SOURCE);
}
function render(): void {
  const map = props.map;
  if (!map?.isStyleLoaded()) return;
  const features = store.origins.filter((o) => store.visible(o.originId)).flatMap((o) =>
    o.sensors.filter((s) => store.visible(`${o.originId}/${s.state.sensorId}`)).flatMap((s) =>
      s.display.geojson.features));
  const data = { type: "FeatureCollection", features } as FeatureCollection;
  const source = map.getSource(SOURCE) as GeoJSONSource | undefined;
  if (source) source.setData(data);
  else {
    map.addSource(SOURCE, { type: "geojson", data });
    map.addLayer({ id: LAYERS[0], source: SOURCE, type: "fill", filter: ["==", ["geometry-type"], "Polygon"],
      paint: { "fill-color": "#e7b55a", "fill-opacity": 0.18, "fill-outline-color": "#e7b55a" } });
    map.addLayer({ id: LAYERS[1], source: SOURCE, type: "line", filter: ["==", ["geometry-type"], "LineString"],
      paint: { "line-color": "#ffd789", "line-width": 2.5 } });
    map.addLayer({ id: LAYERS[2], source: SOURCE, type: "symbol",
      filter: ["all", ["==", ["geometry-type"], "Point"], ["==", ["get", "headingVisible"], true]],
      layout: { "text-field": "↑", "text-font": ["Noto Sans Regular"], "text-size": 30,
        "text-rotate": ["get", "azimuthDeg"], "text-rotation-alignment": "map", "text-allow-overlap": true },
      paint: { "text-color": "#ffd789", "text-halo-color": "#202a30", "text-halo-width": 1 } });
  }
}
watch(() => props.map, (map, previous) => {
  previous?.off("styledata", render);
  remove(previous);
  map?.on("styledata", render);
  render();
});
watch(() => [store.origins, store.visible], render, { deep: true });
// A clock requests fresh native projections; TTL and skew remain native decisions.
onMounted(() => {
  void store.refresh();
  timer = setInterval(() => { void store.refresh(); }, 1000);

});
onBeforeUnmount(() => { clearInterval(timer); props.map?.off("styledata", render); remove(props.map); });
function toggle(key: string): void { store.toggle(key); render(); }
function focus(lon: number, lat: number): void { props.map?.easeTo({ center: [lon, lat], zoom: Math.max(props.map.getZoom(), 14) }); }
function reading(value: number | null, unit: string): string { return value == null ? "Unknown" : `${value.toFixed(1)}${unit}`; }
</script>

<template>
  <details v-if="store.origins.length || store.error" class="sensor-panel" data-testid="sensor-geometry-panel">
    <summary>Sensors <span>{{ store.origins.reduce((n, o) => n + o.sensors.length, 0) }}</span></summary>
    <p v-if="store.error" role="alert">{{ store.error }}</p>
    <p class="sensor-caption">Projected display sectors · no terrain correction</p>
    <section v-for="origin in store.origins" :key="origin.originId">
      <div class="sensor-heading">
        <label><input type="checkbox" :checked="store.visible(origin.originId)" @change="toggle(origin.originId)" /> {{ origin.label }}</label>
        <button v-if="origin.position" type="button" @click="focus(origin.position.lon, origin.position.lat)">Locate</button>
      </div>
      <small>{{ origin.originKind }} · {{ origin.originId.slice(0, 8) }}</small>
      <article v-for="sensor in origin.sensors" :key="sensor.state.sensorId">
        <label><input type="checkbox" :checked="store.visible(`${origin.originId}/${sensor.state.sensorId}`)" @change="toggle(`${origin.originId}/${sensor.state.sensorId}`)" /> {{ sensor.manifest?.label || sensor.state.sensorId }}</label>
        <p class="sensor-status">{{ sensor.display.stale ? "Stale" : "Current" }} · {{ Math.max(0, Math.floor((store.observedAtMs - sensor.state.sampleAtMs) / 1000)) }}s old<span v-if="sensor.display.unsynchronized"> · Position not synchronized</span><span v-if="sensor.display.positionStale"> · Position unavailable or stale</span></p>
        <dl>
          <dt>Boresight / elevation</dt><dd>{{ reading(sensor.state.azimuthDeg, "° true") }} / {{ reading(sensor.state.elevationDeg, "°") }}</dd>
          <dt>Horizontal / vertical FOV</dt><dd>{{ reading(sensor.state.horizontalFovDeg, "°") }} / {{ reading(sensor.state.verticalFovDeg, "°") }}</dd>
          <dt>Range</dt><dd>{{ reading(sensor.state.slantRangeM, " m") }} · {{ sensor.state.rangeKind }}</dd>
          <dt>Roll / image north</dt><dd>{{ reading(sensor.state.rollDeg, "°") }} / {{ reading(sensor.state.imageNorthDeg, "°") }}</dd>
        </dl>
        <div v-if="sensor.manifest?.video" class="sensor-video">
          <p>Video reference available · {{ sensor.manifest.video.protocol }}</p>
          <code>{{ sensor.manifest.video.endpointRef }}</code>
        </div>
        <small v-else>Video unavailable</small>
      </article>
    </section>
  </details>
</template>

<style scoped>
.sensor-panel { position: absolute; left: 12px; bottom: 84px; z-index: 5; width: min(340px, calc(100% - 24px)); max-height: 55%; overflow: auto; padding: 10px 14px; border: 1px solid var(--border-color, #605446); border-radius: 12px; background: var(--surface-color, #202a30); color: var(--text-color, #f3ede1); box-shadow: 0 4px 18px #0005; }
summary { cursor: pointer; font-weight: 700; } summary span { float: right; color: #e7b55a; }
.sensor-caption, small, .sensor-status { font-size: 0.75rem; opacity: 0.8; }
section { border-top: 1px solid #ffffff20; padding-top: 10px; margin-top: 10px; }
.sensor-heading { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
label { display: flex; align-items: center; gap: 8px; } article { padding: 10px 0 2px; }
dl { display: grid; grid-template-columns: 1fr 1fr; font-size: 0.75rem; gap: 4px 8px; } dd { margin: 0; font-variant-numeric: tabular-nums; }
code { overflow-wrap: anywhere; font-size: 0.75rem; } button { padding: 5px 10px; } input { accent-color: #e7b55a; }
</style>
