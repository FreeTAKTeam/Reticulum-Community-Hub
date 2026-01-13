<template>
  <div class="grid gap-6 lg:grid-cols-[2fr,1fr]">
    <BaseCard title="Telemetry Map">
      <div class="mb-4 flex flex-wrap gap-4">
        <BaseInput v-model="topicFilter" label="Topic ID" />
        <BaseInput v-model="search" label="Search Identity" />
        <BaseButton variant="secondary" @click="applyFilters">Apply</BaseButton>
      </div>
      <LoadingSkeleton v-if="telemetry.loading" />
      <div ref="mapContainer" class="h-[480px] rounded border border-rth-border"></div>
    </BaseCard>

    <div class="space-y-4">
      <BaseCard title="Live Markers">
        <LoadingSkeleton v-if="telemetry.loading" />
        <ul v-else class="space-y-2 text-sm">
          <li v-for="marker in filteredMarkers" :key="marker.id" class="cursor-pointer rounded border border-rth-border bg-rth-panel-muted p-3" @click="selectMarker(marker)">
            <div class="font-semibold">{{ marker.name }}</div>
            <div class="text-xs text-rth-muted">{{ marker.lat.toFixed(4) }}, {{ marker.lon.toFixed(4) }}</div>
          </li>
        </ul>
      </BaseCard>
      <BaseCard title="Telemetry Inspector">
        <div v-if="selected">
          <div class="text-sm text-rth-muted">{{ selected.name }}</div>
          <BaseFormattedOutput class="mt-2" :value="selected.raw" />
        </div>
        <div v-else class="text-sm text-rth-muted">Select a marker to inspect telemetry.</div>
      </BaseCard>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted } from "vue";
import { ref } from "vue";
import maplibregl from "maplibre-gl";
import BaseButton from "../components/BaseButton.vue";
import BaseCard from "../components/BaseCard.vue";
import BaseFormattedOutput from "../components/BaseFormattedOutput.vue";
import BaseInput from "../components/BaseInput.vue";
import LoadingSkeleton from "../components/LoadingSkeleton.vue";
import { WsClient } from "../api/ws";
import { useTelemetryStore } from "../stores/telemetry";
import type { TelemetryMarker } from "../utils/telemetry";

const telemetry = useTelemetryStore();
const mapContainer = ref<HTMLDivElement | null>(null);
const mapInstance = ref<maplibregl.Map | null>(null);
const search = ref("");
const topicFilter = ref("");
const selected = ref<TelemetryMarker | null>(null);
const wsClient = ref<WsClient | null>(null);
const defaultStyleUrl = new URL("../assets/map-style.json", import.meta.url).toString();
const mapStyle = import.meta.env.VITE_RTH_MAP_STYLE_URL ?? defaultStyleUrl;
let pollerId: number | undefined;

const filteredMarkers = computed(() => {
  const query = search.value.toLowerCase();
  return telemetry.markers.filter((marker) => {
    if (query && !marker.name.toLowerCase().includes(query)) {
      return false;
    }
    return true;
  });
});

const sinceSeconds = () => Math.floor(Date.now() / 1000) - 3600;

const subscribeTelemetry = () => {
  if (!wsClient.value) {
    return;
  }
  wsClient.value.send({
    type: "telemetry.subscribe",
    ts: new Date().toISOString(),
    data: {
      since: sinceSeconds(),
      topic_id: telemetry.topicId || undefined,
      follow: true
    }
  });
};

const applyFilters = async () => {
  telemetry.topicId = topicFilter.value;
  await telemetry.fetchTelemetry(sinceSeconds());
  renderMarkers();
  subscribeTelemetry();
};

const selectMarker = (marker: TelemetryMarker) => {
  selected.value = marker;
  if (mapInstance.value) {
    mapInstance.value.flyTo({ center: [marker.lon, marker.lat], zoom: 9 });
  }
};

const renderMarkers = () => {
  if (!mapInstance.value) {
    return;
  }
  const map = mapInstance.value;
  const existing = map.getSource("telemetry") as maplibregl.GeoJSONSource | undefined;
  const featureCollection = {
    type: "FeatureCollection",
    features: telemetry.markers.map((marker) => ({
      type: "Feature",
      geometry: {
        type: "Point",
        coordinates: [marker.lon, marker.lat]
      },
      properties: {
        id: marker.id,
        name: marker.name
      }
    }))
  } as GeoJSON.FeatureCollection;

  if (existing) {
    existing.setData(featureCollection);
    return;
  }

  map.addSource("telemetry", {
    type: "geojson",
    data: featureCollection
  });
  map.addLayer({
    id: "telemetry-points",
    type: "circle",
    source: "telemetry",
    paint: {
      "circle-radius": 6,
      "circle-color": "#82DBF7",
      "circle-stroke-color": "#222128",
      "circle-stroke-width": 2
    }
  });
};

onMounted(async () => {
  if (mapContainer.value) {
    mapInstance.value = new maplibregl.Map({
      container: mapContainer.value,
      style: mapStyle,
      center: [0, 0],
      zoom: 1
    });
  }
  await telemetry.fetchTelemetry(sinceSeconds());
  renderMarkers();

  const ws = new WsClient(
    "/telemetry/stream",
    (payload) => {
      if (payload.type === "telemetry.snapshot") {
        telemetry.applySnapshot((payload.data as any).entries ?? []);
        renderMarkers();
      }
      if (payload.type === "telemetry.update") {
        telemetry.applyUpdate((payload.data as any).entry);
        renderMarkers();
      }
    },
    () => {
      subscribeTelemetry();
    }
  );
  ws.connect();
  wsClient.value = ws;

  pollerId = window.setInterval(async () => {
    await telemetry.fetchTelemetry(sinceSeconds());
    renderMarkers();
  }, 60000);
});

onUnmounted(() => {
  if (wsClient.value) {
    wsClient.value.close();
  }
  if (pollerId) {
    window.clearInterval(pollerId);
  }
});
</script>
