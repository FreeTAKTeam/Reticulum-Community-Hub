<template>
  <div class="space-y-6">
    <BaseCard title="Telemetry Map">
      <LoadingSkeleton v-if="telemetry.loading" />
      <div ref="mapContainer" class="h-[720px] w-full rounded border border-rth-border"></div>
      <div class="mt-4 space-y-3">
        <div class="flex flex-wrap items-end gap-4">
          <BaseSelect v-model="markerCategory" label="Marker Type" :options="markerOptions" class="min-w-[240px]" />
          <BaseButton
            :variant="markerMode ? 'success' : 'secondary'"
            icon-left="plus"
            @click="toggleMarkerMode"
          >
            {{ markerMode ? "Click Map to Place" : "Place Marker" }}
          </BaseButton>
          <span v-if="markerMode" class="text-xs text-rth-muted">Click on the map to drop a marker.</span>
        </div>
        <div class="flex flex-wrap items-end gap-4">
          <BaseInput v-model="topicFilter" label="Topic ID" class="min-w-[220px] flex-1" />
          <BaseInput v-model="search" label="Search Identity" class="min-w-[220px] flex-1" />
          <BaseButton variant="secondary" icon-left="filter" @click="applyFilters">Apply</BaseButton>
        </div>
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

    <BaseCard title="Operator Markers">
      <LoadingSkeleton v-if="markersStore.loading" />
      <ul v-else class="space-y-2 text-sm">
        <li
          v-for="marker in markersStore.markers"
          :key="marker.id"
          class="cursor-pointer rounded border border-rth-border bg-rth-panel-muted p-3"
          :class="{ 'opacity-60 line-through': marker.expired }"
          @click="focusOperatorMarker(marker)"
        >
          <div class="font-semibold">{{ marker.name }}</div>
          <div class="text-xs text-rth-muted">
            {{ marker.category }} - {{ marker.lat.toFixed(4) }}, {{ marker.lon.toFixed(4) }}
            <span v-if="marker.expired" class="ml-2 uppercase tracking-wide text-rth-muted">Expired</span>
          </div>
        </li>
      </ul>
    </BaseCard>

    <BaseCard title="Telemetry Markers">
      <LoadingSkeleton v-if="telemetry.loading" />
      <ul v-else class="space-y-2 text-sm">
        <li v-for="marker in filteredMarkers" :key="marker.id" class="cursor-pointer rounded border border-rth-border bg-rth-panel-muted p-3" @click="selectMarker(marker)">
          <div class="font-semibold">{{ marker.name }}</div>
          <div class="text-xs text-rth-muted">{{ marker.lat.toFixed(4) }}, {{ marker.lon.toFixed(4) }}</div>
        </li>
      </ul>
    </BaseCard>

    <BaseModal :open="markerModalOpen" title="Create Marker" @close="closeMarkerModal">
      <div class="space-y-4">
        <div class="grid gap-4 md:grid-cols-2">
          <BaseSelect v-model="markerDraftCategory" label="Type" :options="markerOptions" />
          <BaseInput v-model="markerDraftName" label="Name" />
        </div>
        <BaseInput v-model="markerDraftNotes" label="Notes" />
        <div class="text-xs text-rth-muted">
          Lat {{ markerDraftLat.toFixed(6) }} - Lon {{ markerDraftLon.toFixed(6) }}
        </div>
        <div class="flex justify-end gap-3">
          <BaseButton variant="secondary" @click="closeMarkerModal">Cancel</BaseButton>
          <BaseButton variant="success" icon-left="check" @click="confirmMarker">Create</BaseButton>
        </div>
      </div>
    </BaseModal>
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
import BaseModal from "../components/BaseModal.vue";
import BaseSelect from "../components/BaseSelect.vue";
import LoadingSkeleton from "../components/LoadingSkeleton.vue";
import { WsClient } from "../api/ws";
import { useMarkersStore } from "../stores/markers";
import { useTelemetryStore } from "../stores/telemetry";
import { buildMarkerSymbolKey } from "../utils/markers";
import { defaultMarkerName } from "../utils/markers";
import { markerSymbols } from "../utils/markers";
import { parseMarkerSymbolKey } from "../utils/markers";
import { resolveMarkerSymbolKey } from "../utils/markers";
import { buildTelemetryIconId } from "../utils/telemetry-icons";
import { isTelemetryIconKey } from "../utils/telemetry-icons";
import { resolveTelemetryIconKey } from "../utils/telemetry-icons";
import { telemetryIcons } from "../utils/telemetry-icons";
import { telemetryIconOptions } from "../utils/telemetry-icons";
import type { TelemetryIconKey } from "../utils/telemetry-icons";
import type { TelemetryMarker } from "../utils/telemetry";

const telemetry = useTelemetryStore();
const markersStore = useMarkersStore();
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
let telemetryInteractionReady = false;
let markerInteractionReady = false;
const markerImagesReady = ref(false);
const telemetryIconsReady = ref(false);
const markerMode = ref(false);
const markerCategory = ref<TelemetryIconKey>("marker");
const markerOptions = telemetryIconOptions;
const markerModalOpen = ref(false);
const markerDraftCategory = ref<TelemetryIconKey>("marker");
const markerDraftName = ref("");
const markerDraftNotes = ref("");
const markerDraftLat = ref(0);
const markerDraftLon = ref(0);
const draggingMarkerId = ref<string | null>(null);
const draggingMarkerOrigin = ref<{ lat: number; lon: number } | null>(null);
const dragPositions = ref(new Map<string, { lat: number; lon: number }>());
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

const toggleMarkerMode = () => {
  markerMode.value = !markerMode.value;
};

const openMarkerModal = (lngLat: maplibregl.LngLat) => {
  markerDraftLat.value = lngLat.lat;
  markerDraftLon.value = lngLat.lng;
  markerDraftCategory.value = markerCategory.value;
  if (!markerDraftName.value.trim()) {
    markerDraftName.value = defaultMarkerName(markerDraftCategory.value);
  }
  markerModalOpen.value = true;
  markerMode.value = false;
};

const closeMarkerModal = () => {
  markerModalOpen.value = false;
  markerDraftName.value = "";
  markerDraftNotes.value = "";
  markerDraftCategory.value = markerCategory.value;
};

const confirmMarker = async () => {
  const symbolId = markerDraftCategory.value;
  const name = markerDraftName.value.trim() || defaultMarkerName(symbolId);
  const notes = markerDraftNotes.value.trim();
  const created = await markersStore.createMarker({
    name,
    type: symbolId,
    symbol: symbolId,
    category: symbolId,
    lat: markerDraftLat.value,
    lon: markerDraftLon.value,
    notes: notes || undefined
  });
  markerModalOpen.value = false;
  markerDraftName.value = "";
  markerDraftNotes.value = "";
  markerDraftCategory.value = markerCategory.value;
  renderOperatorMarkers();
  focusOperatorMarker(created);
};

const focusOperatorMarker = (marker: { lat: number; lon: number }) => {
  if (!mapInstance.value) {
    return;
  }
  mapInstance.value.flyTo({ center: [marker.lon, marker.lat], zoom: 9 });
};

const handleMapClick = (event: maplibregl.MapMouseEvent) => {
  if (!markerMode.value) {
    return;
  }
  openMarkerModal(event.lngLat);
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

const markerIconBase = import.meta.env.BASE_URL ?? "/";
const markerIconRoot = markerIconBase.endsWith("/") ? markerIconBase : `${markerIconBase}/`;
const MAKI_ICON_PIXEL_SIZE = 15;
const NAPSG_ICON_PIXEL_SIZE = 91;
const MAKI_ICON_SCALE = 0.9;
const NAPSG_ICON_SCALE = (MAKI_ICON_PIXEL_SIZE / NAPSG_ICON_PIXEL_SIZE) * MAKI_ICON_SCALE;
const BASE_ICON_ZOOM = 1;
const TELEMETRY_ICON_SCALE = 0.85;
const TELEMETRY_ICON_COLOR = "#82DBF7";

const resolveIconScale = (symbolSet?: string) => {
  return symbolSet === "napsg" ? NAPSG_ICON_SCALE : MAKI_ICON_SCALE;
};

const resolveZoomScale = (zoom: number) => {
  return Math.pow(1.1, zoom - BASE_ICON_ZOOM);
};

const buildIconSizeExpression = (zoom: number) => {
  return [
    "*",
    ["coalesce", ["get", "iconScale"], MAKI_ICON_SCALE],
    resolveZoomScale(zoom)
  ];
};

const buildTelemetryIconSizeExpression = (zoom: number) => {
  return ["*", TELEMETRY_ICON_SCALE, resolveZoomScale(zoom)];
};

const handleMarkerZoom = () => {
  if (!mapInstance.value) {
    return;
  }
  const map = mapInstance.value;
  const layerId = "operator-marker-layer";
  if (map.getLayer(layerId)) {
    map.setLayoutProperty(layerId, "icon-size", buildIconSizeExpression(map.getZoom()));
  }
  const telemetryLayerId = "telemetry-icons";
  if (map.getLayer(telemetryLayerId)) {
    map.setLayoutProperty(
      telemetryLayerId,
      "icon-size",
      buildTelemetryIconSizeExpression(map.getZoom())
    );
  }
};

const isSdfMarkerImage = (symbolKey: string) => {
  if (symbolKey === "marker-fallback") {
    return true;
  }
  const parsed = parseMarkerSymbolKey(symbolKey);
  return parsed.set !== "napsg";
};

const markerIconUrl = (symbolSet: string, symbolId: string) => {
  return `${markerIconRoot}icons/${symbolSet}/${symbolId}.svg`;
};
const markerFallbackUrl = `${markerIconRoot}icons/marker-fallback.svg`;
const svgToDataUrl = (svg: string) => `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;

const rasterizeImage = async (url: string) => {
  const image = new Image();
  image.crossOrigin = "anonymous";
  const loadPromise = new Promise<HTMLImageElement>((resolve, reject) => {
    image.onload = () => resolve(image);
    image.onerror = (error) => reject(error);
  });
  image.src = url;
  await loadPromise;
  const width = image.naturalWidth || image.width || 32;
  const height = image.naturalHeight || image.height || 32;
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  if (!context) {
    throw new Error("Unable to create canvas context for marker icon.");
  }
  context.clearRect(0, 0, width, height);
  context.drawImage(image, 0, 0, width, height);
  return context.getImageData(0, 0, width, height);
};

const loadMarkerImage = async (map: maplibregl.Map, id: string, url: string, sdf: boolean) => {
  if (map.hasImage(id)) {
    return;
  }
  try {
    const imageData = await rasterizeImage(url);
    map.addImage(id, imageData, { sdf });
  } catch (error) {
    console.warn(`Failed to load marker icon ${id} from ${url}.`, error);
  }
};

const loadMarkerImages = async () => {
  if (!mapInstance.value) {
    return;
  }
  const map = mapInstance.value;
  await loadMarkerImage(map, "marker-fallback", markerFallbackUrl, true);
  await Promise.all(
    markerSymbols.value.map((symbol) => {
      const symbolKey = buildMarkerSymbolKey(symbol.set, symbol.id);
      return loadMarkerImage(
        map,
        symbolKey,
        markerIconUrl(symbol.set, symbol.id),
        isSdfMarkerImage(symbolKey)
      );
    })
  );
  markerImagesReady.value = true;
};

const loadTelemetryIcons = async () => {
  if (!mapInstance.value) {
    return;
  }
  const map = mapInstance.value;
  await Promise.all(
    telemetryIcons.map((icon) =>
      loadMarkerImage(map, buildTelemetryIconId(icon.key), svgToDataUrl(icon.svg), true)
    )
  );
  telemetryIconsReady.value = true;
};

const buildOperatorFeatureCollection = () =>
  ({
    type: "FeatureCollection",
    features: markersStore.markers.filter((marker) => !marker.expired).map((marker) => {
      const override = dragPositions.value.get(marker.id);
      const lat = override?.lat ?? marker.lat;
      const lon = override?.lon ?? marker.lon;
      const mdiKey = isTelemetryIconKey(marker.symbol)
        ? marker.symbol
        : isTelemetryIconKey(marker.category)
          ? marker.category
          : undefined;
      const symbolKey = mdiKey
        ? buildTelemetryIconId(mdiKey)
        : resolveMarkerSymbolKey(marker.symbol, marker.symbolSet ?? marker.category);
      const iconScale = mdiKey
        ? TELEMETRY_ICON_SCALE
        : resolveIconScale(marker.symbolSet ?? marker.category);
      return {
        type: "Feature",
        geometry: {
          type: "Point",
          coordinates: [lon, lat]
        },
        properties: {
          id: marker.id,
          name: marker.name,
          symbol: symbolKey,
          iconScale,
          color: marker.color
        }
      };
    })
  }) as GeoJSON.FeatureCollection;

const startMarkerDrag = (event: maplibregl.MapMouseEvent & maplibregl.EventData) => {
  if (!mapInstance.value || markerMode.value) {
    return;
  }
  const feature = event.features?.[0];
  const markerId = feature?.properties?.id;
  if (!markerId) {
    return;
  }
  const marker = markersStore.markerIndex.get(String(markerId));
  if (!marker) {
    return;
  }
  draggingMarkerId.value = marker.id;
  draggingMarkerOrigin.value = { lat: marker.lat, lon: marker.lon };
  mapInstance.value.getCanvas().style.cursor = "grabbing";
  mapInstance.value.dragPan.disable();
  mapInstance.value.on("mousemove", handleMarkerDrag);
  mapInstance.value.once("mouseup", finishMarkerDrag);
  mapInstance.value.once("mouseleave", finishMarkerDrag);
};

const handleMarkerDrag = (event: maplibregl.MapMouseEvent & maplibregl.EventData) => {
  if (!draggingMarkerId.value) {
    return;
  }
  dragPositions.value.set(draggingMarkerId.value, {
    lat: event.lngLat.lat,
    lon: event.lngLat.lng
  });
  renderOperatorMarkers();
};

const finishMarkerDrag = () => {
  if (!mapInstance.value) {
    return;
  }
  const markerId = draggingMarkerId.value;
  const origin = draggingMarkerOrigin.value;
  const override = markerId ? dragPositions.value.get(markerId) : undefined;
  draggingMarkerId.value = null;
  draggingMarkerOrigin.value = null;
  if (markerId) {
    dragPositions.value.delete(markerId);
  }
  mapInstance.value.off("mousemove", handleMarkerDrag);
  mapInstance.value.dragPan.enable();
  mapInstance.value.getCanvas().style.cursor = "";
  renderOperatorMarkers();
  if (markerId && origin && override) {
    if (origin.lat !== override.lat || origin.lon !== override.lon) {
      void markersStore.updateMarkerPosition(markerId, override.lat, override.lon).then(() => {
        renderOperatorMarkers();
      });
    }
  }
};

const stopMarkerDrag = () => {
  if (!mapInstance.value) {
    return;
  }
  mapInstance.value.off("mousemove", handleMarkerDrag);
  mapInstance.value.dragPan.enable();
  mapInstance.value.getCanvas().style.cursor = "";
  draggingMarkerId.value = null;
  draggingMarkerOrigin.value = null;
};

const renderTelemetryMarkers = () => {
  if (!mapInstance.value || !mapReady.value || !telemetryIconsReady.value) {
    return;
  }
  const map = mapInstance.value;
  const sourceId = "telemetry";
  const layerId = "telemetry-icons";
  const existing = map.getSource(sourceId) as maplibregl.GeoJSONSource | undefined;
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
        name: marker.name,
        icon: buildTelemetryIconId(resolveTelemetryIconKey(marker.raw))
      }
    }))
  } as GeoJSON.FeatureCollection;

  if (existing) {
    existing.setData(featureCollection);
  }

  if (!existing) {
    map.addSource(sourceId, {
      type: "geojson",
      data: featureCollection
    });
    map.addLayer({
      id: layerId,
      type: "symbol",
      source: sourceId,
      layout: {
        "icon-image": ["coalesce", ["image", ["get", "icon"]], ["image", "mdi-marker"]],
        "icon-size": buildTelemetryIconSizeExpression(map.getZoom()),
        "icon-allow-overlap": true
      },
      paint: {
        "icon-color": TELEMETRY_ICON_COLOR
      }
    });
  }

  if (!telemetryInteractionReady) {
    map.on("click", layerId, (event) => {
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
    map.on("mouseenter", layerId, () => {
      map.getCanvas().style.cursor = "pointer";
    });
    map.on("mouseleave", layerId, () => {
      map.getCanvas().style.cursor = "";
    });
    map.on("move", () => {
      if (inspectorOpen.value && selected.value) {
        updateInspectorPosition(selected.value);
      }
    });
    telemetryInteractionReady = true;
  }
};

const renderOperatorMarkers = () => {
  if (!mapInstance.value || !mapReady.value || !markerImagesReady.value || !telemetryIconsReady.value) {
    return;
  }
  const map = mapInstance.value;
  const sourceId = "operator-markers";
  const layerId = "operator-marker-layer";
  const featureCollection = buildOperatorFeatureCollection();
  const existing = map.getSource(sourceId) as maplibregl.GeoJSONSource | undefined;
  if (existing) {
    existing.setData(featureCollection);
  } else {
    map.addSource(sourceId, {
      type: "geojson",
      data: featureCollection
    });
    map.addLayer({
      id: layerId,
      type: "symbol",
      source: sourceId,
      layout: {
        "icon-image": ["coalesce", ["image", ["get", "symbol"]], ["image", "marker-fallback"]],
        "icon-size": buildIconSizeExpression(map.getZoom()),
        "icon-allow-overlap": true
      },
      paint: {
        "icon-color": ["coalesce", ["get", "color"], "#FBBF24"]
      }
    });
  }

  handleMarkerZoom();

  if (!markerInteractionReady) {
    map.on("mousedown", layerId, startMarkerDrag);
    map.on("zoom", handleMarkerZoom);
    map.on("mouseenter", layerId, () => {
      if (!draggingMarkerId.value) {
        map.getCanvas().style.cursor = "move";
      }
    });
    map.on("mouseleave", layerId, () => {
      if (!draggingMarkerId.value) {
        map.getCanvas().style.cursor = "";
      }
    });
    markerInteractionReady = true;
  }
};

const renderMarkers = () => {
  renderTelemetryMarkers();
  renderOperatorMarkers();
};

const loadMarkerSymbols = async () => {
  try {
    await markersStore.fetchMarkerSymbols();
  } catch (error) {
    console.warn("Failed to load marker symbols.", error);
  }
};

onMounted(async () => {
  const symbolsPromise = loadMarkerSymbols();
  if (mapContainer.value) {
    mapInstance.value = new maplibregl.Map({
      container: mapContainer.value,
      style: mapStyle,
      center: [0, 0],
      zoom: 1
    });
    mapInstance.value.on("load", async () => {
      mapReady.value = true;
      await symbolsPromise;
      await loadMarkerImages();
      await loadTelemetryIcons();
      renderMarkers();
      mapInstance.value?.on("click", handleMapClick);
    });
  }
  await telemetry.fetchTelemetry(sinceSeconds());
  await symbolsPromise;
  await markersStore.fetchMarkers();
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
    await markersStore.fetchMarkers();
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
  if (mapInstance.value) {
    mapInstance.value.off("zoom", handleMarkerZoom);
  }
  window.removeEventListener("resize", handleInspectorViewportChange);
  window.removeEventListener("scroll", handleInspectorViewportChange);
  stopDrag();
  stopMarkerDrag();
});
</script>
