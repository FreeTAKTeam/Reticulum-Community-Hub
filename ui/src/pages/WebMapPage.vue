<template>
  <div class="space-y-6">
    <BaseCard title="Telemetry Map">
      <LoadingSkeleton v-if="telemetry.loading" />
      <div ref="mapContainer" class="h-[720px] w-full rounded border border-rth-border"></div>
      <div class="mt-4 flex flex-wrap items-end gap-4">
        <BaseInput v-model="topicFilter" label="Topic ID" class="min-w-[220px] flex-1" />
        <BaseInput v-model="search" label="Search Identity" class="min-w-[220px] flex-1" />
        <BaseButton variant="secondary" icon-left="filter" @click="applyFilters">Apply</BaseButton>
      </div>
    </BaseCard>

    <div
      v-if="inspectorOpen && selected"
      ref="inspectorRef"
      class="cui-map-inspector"
      :style="inspectorStyle"
    >
      <div class="cui-map-inspector__titlebar flex items-start justify-between gap-3" @mousedown="startDrag">
        <div>
          <div class="text-sm font-semibold">{{ selected.name }}</div>
          <div class="text-xs text-rth-muted">Telemetry Inspector</div>
        </div>
        <button class="cui-modal-close" aria-label="Close" @click="closeInspector" @mousedown.stop>X</button>
      </div>
      <BaseFormattedOutput class="mt-3" :value="selected.raw" :accordion-open-by-default="false" />
    </div>

    <BaseCard title="Live Markers">
      <LoadingSkeleton v-if="telemetry.loading" />
      <ul v-else class="space-y-2 text-sm">
        <li v-for="marker in filteredMarkers" :key="marker.id" class="cursor-pointer rounded border border-rth-border bg-rth-panel-muted p-3" @click="selectMarker(marker)">
          <div class="font-semibold">{{ marker.name }}</div>
          <div class="text-xs text-rth-muted">{{ marker.lat.toFixed(4) }}, {{ marker.lon.toFixed(4) }}</div>
        </li>
      </ul>
    </BaseCard>
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
const mapReady = ref(false);
const search = ref("");
const topicFilter = ref("");
const selected = ref<TelemetryMarker | null>(null);
const inspectorOpen = ref(false);
const inspectorPosition = ref({ left: 0, top: 0 });
const inspectorPinned = ref(false);
const inspectorRef = ref<HTMLDivElement | null>(null);
const dragging = ref(false);
const dragOffset = ref({ x: 0, y: 0 });
const wsClient = ref<WsClient | null>(null);
const defaultStyleUrl = new URL("../assets/map-style.json", import.meta.url).toString();
const mapStyle = import.meta.env.VITE_RTH_MAP_STYLE_URL ?? defaultStyleUrl;
let pollerId: number | undefined;
let mapInteractionReady = false;
const handleInspectorViewportChange = () => {
  if (inspectorOpen.value && selected.value) {
    updateInspectorPosition(selected.value);
  }
};

const filteredMarkers = computed(() => {
  const query = search.value.toLowerCase();
  return telemetry.markers.filter((marker) => {
    if (query && !marker.name.toLowerCase().includes(query)) {
      return false;
    }
    return true;
  });
});

const markerIndex = computed(() => {
  const map = new Map<string, TelemetryMarker>();
  telemetry.markers.forEach((marker) => {
    map.set(marker.id, marker);
  });
  return map;
});

const inspectorStyle = computed(() => ({
  left: `${inspectorPosition.value.left}px`,
  top: `${inspectorPosition.value.top}px`,
  transform: inspectorPinned.value ? "translate(0, 0)" : "translate(-50%, -100%)"
}));

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
  openInspector(marker, true);
};

const closeInspector = () => {
  inspectorOpen.value = false;
  inspectorPinned.value = false;
};

const updateInspectorPosition = (marker?: TelemetryMarker) => {
  const target = marker ?? selected.value;
  if (!target || !mapInstance.value || !mapContainer.value || inspectorPinned.value) {
    return;
  }
  const point = mapInstance.value.project([target.lon, target.lat]);
  const rect = mapContainer.value.getBoundingClientRect();
  const width = 630;
  const height = 300;
  const padding = 12;
  const rawLeft = rect.left + point.x;
  const rawTop = rect.top + point.y;
  const minLeft = width / 2 + padding;
  const maxLeft = window.innerWidth - width / 2 - padding;
  const minTop = height + padding;
  const maxTop = window.innerHeight - padding;
  const left = Math.min(Math.max(rawLeft, minLeft), maxLeft);
  const top = Math.min(Math.max(rawTop, minTop), maxTop);
  inspectorPosition.value = { left, top };
};

const openInspector = (marker: TelemetryMarker, flyTo = false) => {
  selected.value = marker;
  inspectorOpen.value = true;
  inspectorPinned.value = false;
  if (mapInstance.value) {
    if (flyTo) {
      mapInstance.value.flyTo({ center: [marker.lon, marker.lat], zoom: 9 });
      updateInspectorPosition(marker);
      mapInstance.value.once("moveend", () => updateInspectorPosition(marker));
    } else {
      updateInspectorPosition(marker);
    }
  }
};

const startDrag = (event: MouseEvent) => {
  if (event.button !== 0 || !inspectorRef.value) {
    return;
  }
  dragging.value = true;
  inspectorPinned.value = true;
  const rect = inspectorRef.value.getBoundingClientRect();
  dragOffset.value = {
    x: event.clientX - rect.left,
    y: event.clientY - rect.top
  };
  window.addEventListener("mousemove", handleDrag);
  window.addEventListener("mouseup", stopDrag);
};

const handleDrag = (event: MouseEvent) => {
  if (!dragging.value || !inspectorRef.value) {
    return;
  }
  const rect = inspectorRef.value.getBoundingClientRect();
  const width = rect.width || 420;
  const height = rect.height || 300;
  const padding = 8;
  const left = Math.min(Math.max(event.clientX - dragOffset.value.x, padding), window.innerWidth - width - padding);
  const top = Math.min(Math.max(event.clientY - dragOffset.value.y, padding), window.innerHeight - height - padding);
  inspectorPosition.value = { left, top };
};

const stopDrag = () => {
  dragging.value = false;
  window.removeEventListener("mousemove", handleDrag);
  window.removeEventListener("mouseup", stopDrag);
};

const renderMarkers = () => {
  if (!mapInstance.value || !mapReady.value) {
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

  if (!mapInteractionReady) {
    map.on("click", "telemetry-points", (event) => {
      const feature = event.features?.[0];
      const markerId = feature?.properties?.id;
      if (!markerId) {
        return;
      }
      const marker = markerIndex.value.get(String(markerId));
      if (marker) {
        openInspector(marker);
      }
    });
    map.on("mouseenter", "telemetry-points", () => {
      map.getCanvas().style.cursor = "pointer";
    });
    map.on("mouseleave", "telemetry-points", () => {
      map.getCanvas().style.cursor = "";
    });
    map.on("move", () => {
      if (inspectorOpen.value && selected.value) {
        updateInspectorPosition(selected.value);
      }
    });
    mapInteractionReady = true;
  }
};

onMounted(async () => {
  if (mapContainer.value) {
    mapInstance.value = new maplibregl.Map({
      container: mapContainer.value,
      style: mapStyle,
      center: [0, 0],
      zoom: 1
    });
    mapInstance.value.on("load", () => {
      mapReady.value = true;
      renderMarkers();
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

  window.addEventListener("resize", handleInspectorViewportChange);
  window.addEventListener("scroll", handleInspectorViewportChange);
});

onUnmounted(() => {
  if (wsClient.value) {
    wsClient.value.close();
  }
  if (pollerId) {
    window.clearInterval(pollerId);
  }
  window.removeEventListener("resize", handleInspectorViewportChange);
  window.removeEventListener("scroll", handleInspectorViewportChange);
  stopDrag();
});
</script>
