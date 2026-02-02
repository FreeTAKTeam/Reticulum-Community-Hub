<template>
  <div class="space-y-6">
    <div class="flex flex-col gap-6 xl:flex-row">
      <BaseCard title="Telemetry Map" class="flex-1 min-w-0">
        <LoadingSkeleton v-if="telemetry.loading" />
        <div class="relative">
          <div ref="mapContainer" class="h-[720px] w-full rounded border border-rth-border"></div>
          <div class="cui-map-coordinates" aria-live="polite">
            <div class="cui-map-coordinates__row">
              <span class="cui-map-coordinates__label">Lat</span>
              <span class="cui-map-coordinates__value">{{ coordinateLat }}</span>
            </div>
            <div class="cui-map-coordinates__row">
              <span class="cui-map-coordinates__label">Lon</span>
              <span class="cui-map-coordinates__value">{{ coordinateLon }}</span>
            </div>
          </div>
        </div>
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
        class="cui-panel flex flex-col transition-all duration-300 ease-out"
        :class="markersPanelCollapsed ? 'w-full xl:w-12 p-2' : 'w-full xl:w-96 p-4'"
      >
        <div class="flex items-center justify-between gap-2">
          <div v-if="!markersPanelCollapsed" class="text-sm font-semibold text-rth-text">Markers</div>
          <BaseButton
            variant="secondary"
            size="sm"
            :icon-left="markersPanelCollapsed ? 'chevron-left' : 'chevron-right'"
            icon-only
            :aria-label="markersPanelCollapsed ? 'Expand markers panel' : 'Collapse markers panel'"
            :title="markersPanelCollapsed ? 'Expand markers panel' : 'Collapse markers panel'"
            :aria-expanded="!markersPanelCollapsed"
            @click="toggleMarkersPanel"
          />
        </div>
        <div
          v-if="markersPanelCollapsed"
          class="mt-3 flex flex-1 items-center justify-center text-[10px] uppercase tracking-[0.3em] text-rth-muted"
          style="writing-mode: vertical-rl; text-orientation: upright;"
        >
          Markers
        </div>
        <div v-else class="mt-4">
          <div class="flex flex-wrap items-center gap-2 border-b border-rth-border pb-3">
            <BaseButton
              variant="tab"
              size="sm"
              :class="{ 'cui-tab-active': activeMarkerTab === 'operator' }"
              @click="activeMarkerTab = 'operator'"
            >
              Operator Markers
            </BaseButton>
            <BaseButton
              variant="tab"
              size="sm"
              :class="{ 'cui-tab-active': activeMarkerTab === 'telemetry' }"
              @click="activeMarkerTab = 'telemetry'"
            >
              Telemetry Markers
            </BaseButton>
          </div>

          <div v-if="activeMarkerTab === 'operator'" class="mt-4">
            <LoadingSkeleton v-if="markersStore.loading" />
            <ul v-else class="space-y-2 text-sm">
              <li
                v-for="marker in operatorPagination.items"
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
            <div
              v-if="!markersStore.loading"
              class="mt-3 flex flex-wrap items-center justify-between gap-3 text-xs text-rth-muted"
            >
              <span v-if="operatorPagination.total">
                Showing {{ operatorPagination.startIndex }}-{{ operatorPagination.endIndex }} of
                {{ operatorPagination.total }}
              </span>
              <span v-else>No markers yet.</span>
              <div class="flex items-center gap-2">
                <BaseButton
                  variant="secondary"
                  size="sm"
                  iconLeft="chevron-left"
                  :disabled="operatorPagination.page <= 1"
                  @click="updateOperatorPage(-1)"
                >
                  Prev
                </BaseButton>
                <span class="min-w-[96px] text-center">
                  Page {{ operatorPagination.page }} / {{ operatorPagination.totalPages }}
                </span>
                <BaseButton
                  variant="secondary"
                  size="sm"
                  iconRight="chevron-right"
                  :disabled="operatorPagination.page >= operatorPagination.totalPages"
                  @click="updateOperatorPage(1)"
                >
                  Next
                </BaseButton>
              </div>
            </div>
          </div>

          <div v-else class="mt-4">
            <LoadingSkeleton v-if="telemetry.loading" />
            <ul v-else class="space-y-2 text-sm">
              <li
                v-for="marker in telemetryPagination.items"
                :key="marker.id"
                class="cursor-pointer rounded border border-rth-border bg-rth-panel-muted p-3"
                @click="selectMarker(marker)"
              >
                <div class="font-semibold">{{ marker.name }}</div>
                <div class="text-xs text-rth-muted">{{ marker.lat.toFixed(4) }}, {{ marker.lon.toFixed(4) }}</div>
              </li>
            </ul>
            <div
              v-if="!telemetry.loading"
              class="mt-3 flex flex-wrap items-center justify-between gap-3 text-xs text-rth-muted"
            >
              <span v-if="telemetryPagination.total">
                Showing {{ telemetryPagination.startIndex }}-{{ telemetryPagination.endIndex }} of
                {{ telemetryPagination.total }}
              </span>
              <span v-else>No telemetry markers yet.</span>
              <div class="flex items-center gap-2">
                <BaseButton
                  variant="secondary"
                  size="sm"
                  iconLeft="chevron-left"
                  :disabled="telemetryPagination.page <= 1"
                  @click="updateTelemetryPage(-1)"
                >
                  Prev
                </BaseButton>
                <span class="min-w-[96px] text-center">
                  Page {{ telemetryPagination.page }} / {{ telemetryPagination.totalPages }}
                </span>
                <BaseButton
                  variant="secondary"
                  size="sm"
                  iconRight="chevron-right"
                  :disabled="telemetryPagination.page >= telemetryPagination.totalPages"
                  @click="updateTelemetryPage(1)"
                >
                  Next
                </BaseButton>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

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
import { computed, nextTick, onMounted, onUnmounted, watch } from "vue";
import { ref } from "vue";
import { storeToRefs } from "pinia";
import maplibregl from "maplibre-gl";
import BaseButton from "../components/BaseButton.vue";
import BaseCard from "../components/BaseCard.vue";
import BaseFormattedOutput from "../components/BaseFormattedOutput.vue";
import BaseInput from "../components/BaseInput.vue";
import BaseModal from "../components/BaseModal.vue";
import BaseSelect from "../components/BaseSelect.vue";
import LoadingSkeleton from "../components/LoadingSkeleton.vue";
import { WsClient } from "../api/ws";
import { useMapSettingsStore } from "../stores/map-settings";
import { useNavStore } from "../stores/nav";
import { useMarkersStore } from "../stores/markers";
import { useTelemetryStore } from "../stores/telemetry";
import { buildMarkerSymbolKey } from "../utils/markers";
import { defaultMarkerName } from "../utils/markers";
import { getMarkerSymbol } from "../utils/markers";
import { markerSymbols } from "../utils/markers";
import { resolveClusterRadius } from "../utils/map-cluster";
import { resolveZoomScale } from "../utils/map-cluster";
import { loadMdiSvg } from "../utils/mdi-icons";
import { buildTelemetryIconId } from "../utils/telemetry-icons";
import { resolveTelemetryIconValue } from "../utils/telemetry-icons";
import type { TelemetryMarker } from "../utils/telemetry";

const telemetry = useTelemetryStore();
const markersStore = useMarkersStore();
const mapSettingsStore = useMapSettingsStore();
const navStore = useNavStore();
const { isCollapsed: isNavCollapsed } = storeToRefs(navStore);
const { mapView, showMarkerLabels } = storeToRefs(mapSettingsStore);
const mapContainer = ref<HTMLDivElement | null>(null);
const mapInstance = ref<maplibregl.Map | null>(null);
const mapReady = ref(false);
const mapCoordinates = ref<{ lat: number; lon: number } | null>(null);
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
const defaultMapView = { lat: 0, lon: 0, zoom: 1 };
let pollerId: number | undefined;
let telemetryInteractionReady = false;
let telemetryIconInteractionReady = false;
let markerInteractionReady = false;
let telemetryClusterRadius: number | null = null;
let operatorClusterRadius: number | null = null;
const markerImagesReady = ref(false);
const telemetryIconsReady = ref(false);
const markerMode = ref(false);
const markersPanelCollapsed = ref(true);
const markerCategory = ref<string>("marker");
const markerOptions = computed(() =>
  markerSymbols.value.map((symbol) => ({
    label: symbol.label,
    value: symbol.id
  }))
);
const symbolKeySet = computed(
  () => new Set(markerSymbols.value.filter((symbol) => symbol.set !== "napsg").map((symbol) => symbol.id))
);
const markerModalOpen = ref(false);
const markerDraftCategory = ref<string>("marker");
const markerDraftName = ref("");
const markerDraftNotes = ref("");
const markerDraftLat = ref(0);
const markerDraftLon = ref(0);
const draggingMarkerId = ref<string | null>(null);
const draggingMarkerOrigin = ref<{ lat: number; lon: number } | null>(null);
const dragPositions = ref(new Map<string, { lat: number; lon: number }>());
type MarkerTab = "operator" | "telemetry";
const activeMarkerTab = ref<MarkerTab>("operator");
const ITEMS_PER_PAGE = 10;
const operatorPage = ref(1);
const telemetryPage = ref(1);

const formatCoordinate = (value: number | null | undefined) => {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "--";
  }
  return value.toFixed(6);
};

const coordinateLat = computed(() => formatCoordinate(mapCoordinates.value?.lat));
const coordinateLon = computed(() => formatCoordinate(mapCoordinates.value?.lon));

const toTimestamp = (value?: string) => {
  if (!value) {
    return 0;
  }
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : 0;
};
const ensureMarkerSelection = () => {
  if (!markerSymbols.value.length) {
    return;
  }
  if (!markerSymbols.value.some((symbol) => symbol.id === markerCategory.value)) {
    markerCategory.value = markerSymbols.value[0].id;
  }
  if (!markerSymbols.value.some((symbol) => symbol.id === markerDraftCategory.value)) {
    markerDraftCategory.value = markerCategory.value;
  }
};
const handleInspectorViewportChange = () => {
  if (inspectorOpen.value && selected.value) {
    updateInspectorPosition(selected.value);
  }
};

const telemetryMarkersFiltered = computed(() => {
  const query = search.value.toLowerCase();
  return telemetry.markers.filter((marker) => {
    if (query && !marker.name.toLowerCase().includes(query)) {
      return false;
    }
    return true;
  });
});

const telemetryMarkersSorted = computed(() => {
  return [...telemetryMarkersFiltered.value].sort(
    (left, right) => toTimestamp(right.updatedAt) - toTimestamp(left.updatedAt)
  );
});

const operatorMarkersSorted = computed(() => {
  return [...markersStore.markers].sort((left, right) => {
    const leftTime = toTimestamp(left.updatedAt ?? left.time ?? left.createdAt);
    const rightTime = toTimestamp(right.updatedAt ?? right.time ?? right.createdAt);
    return rightTime - leftTime;
  });
});

const buildPagination = <T>(items: T[], page: number) => {
  const total = items.length;
  const totalPages = Math.max(1, Math.ceil(total / ITEMS_PER_PAGE));
  const currentPage = Math.min(Math.max(page, 1), totalPages);
  const startIndex = total === 0 ? 0 : (currentPage - 1) * ITEMS_PER_PAGE + 1;
  const endIndex = total === 0 ? 0 : Math.min(currentPage * ITEMS_PER_PAGE, total);
  return {
    items: items.slice(startIndex ? startIndex - 1 : 0, endIndex),
    total,
    totalPages,
    page: currentPage,
    startIndex,
    endIndex
  };
};

const operatorPagination = computed(() => buildPagination(operatorMarkersSorted.value, operatorPage.value));
const telemetryPagination = computed(() => buildPagination(telemetryMarkersSorted.value, telemetryPage.value));

const updateOperatorPage = (delta: number) => {
  const totalPages = operatorPagination.value.totalPages;
  operatorPage.value = Math.min(totalPages, Math.max(1, operatorPage.value + delta));
};

const updateTelemetryPage = (delta: number) => {
  const totalPages = telemetryPagination.value.totalPages;
  telemetryPage.value = Math.min(totalPages, Math.max(1, telemetryPage.value + delta));
};

watch(
  () => operatorMarkersSorted.value.length,
  (total) => {
    const totalPages = Math.max(1, Math.ceil(total / ITEMS_PER_PAGE));
    if (operatorPage.value > totalPages) {
      operatorPage.value = totalPages;
    }
  }
);

watch(
  () => telemetryMarkersSorted.value.length,
  (total) => {
    const totalPages = Math.max(1, Math.ceil(total / ITEMS_PER_PAGE));
    if (telemetryPage.value > totalPages) {
      telemetryPage.value = totalPages;
    }
  }
);

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
  telemetryPage.value = 1;
  await telemetry.fetchTelemetry(sinceSeconds());
  renderMarkers();
  subscribeTelemetry();
};

const toggleMarkerMode = () => {
  markerMode.value = !markerMode.value;
};

const syncMapCoordinates = (lngLat?: maplibregl.LngLat) => {
  if (lngLat) {
    mapCoordinates.value = { lat: lngLat.lat, lon: lngLat.lng };
    return;
  }
  if (mapInstance.value) {
    const center = mapInstance.value.getCenter();
    mapCoordinates.value = { lat: center.lat, lon: center.lng };
  }
};

const handleMapPointerMove = (event: maplibregl.MapMouseEvent) => {
  syncMapCoordinates(event.lngLat);
};

const handleMapPointerLeave = () => {
  syncMapCoordinates();
};

const scheduleMapResize = async () => {
  await nextTick();
  mapInstance.value?.resize();
  window.setTimeout(() => {
    mapInstance.value?.resize();
  }, 320);
};

watch(isNavCollapsed, () => {
  void scheduleMapResize();
});

const toggleMarkersPanel = async () => {
  markersPanelCollapsed.value = !markersPanelCollapsed.value;
  await scheduleMapResize();
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
const resolveCssColor = (name: string, fallback: string) => {
  if (typeof window === "undefined" || typeof document === "undefined") {
    return fallback;
  }
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
};
const MDI_ICON_PIXEL_SIZE = 24;
const NAPSG_ICON_PIXEL_SIZE = 91;
const TELEMETRY_ICON_SCALE = 0.153;
const NAPSG_ICON_SCALE = (MDI_ICON_PIXEL_SIZE / NAPSG_ICON_PIXEL_SIZE) * TELEMETRY_ICON_SCALE;
const MARKER_PRIMARY_COLOR = resolveCssColor("--cui-primary", "#00b4ff");
const MARKER_ICON_COLOR = MARKER_PRIMARY_COLOR;
const MARKER_ICON_HALO_WIDTH = 1.2;
const TELEMETRY_ICON_COLOR = MARKER_ICON_COLOR;
const MARKER_CLUSTER_FILL_COLOR = "transparent";
const MARKER_CLUSTER_FILL_OPACITY = 0;
const TELEMETRY_CLUSTER_MAX_ZOOM = 12;
const MARKER_LABEL_COLOR = "#E7ECF5";
const MARKER_LABEL_HALO_COLOR = "#06121E";
const MARKER_LABEL_HALO_WIDTH = 1.2;
const MARKER_LABEL_OFFSET: [number, number] = [0, 1.2];
const MARKER_LABEL_SIZE = 12;

const resolveMarkerLabelField = () => (showMarkerLabels.value ? ["get", "name"] : "");

const buildMarkerLabelLayout = () => ({
  "text-field": resolveMarkerLabelField(),
  "text-size": MARKER_LABEL_SIZE,
  "text-offset": MARKER_LABEL_OFFSET,
  "text-anchor": "top",
  "text-allow-overlap": true,
  "text-ignore-placement": true
});

const markerLabelPaint = {
  "text-color": MARKER_LABEL_COLOR,
  "text-halo-color": MARKER_LABEL_HALO_COLOR,
  "text-halo-width": MARKER_LABEL_HALO_WIDTH
};

const buildIconSizeExpression = (zoom: number) => {
  return [
    "*",
    ["coalesce", ["get", "iconScale"], TELEMETRY_ICON_SCALE],
    resolveZoomScale(zoom)
  ];
};

const buildTelemetryIconSizeExpression = (zoom: number) => {
  return ["*", TELEMETRY_ICON_SCALE, resolveZoomScale(zoom)];
};

const applyMarkerLabelVisibility = () => {
  if (!mapInstance.value || !mapReady.value) {
    return;
  }
  const map = mapInstance.value;
  const labelField = resolveMarkerLabelField();
  const layerIds = ["telemetry-icons", "operator-marker-layer"];
  layerIds.forEach((layerId) => {
    if (map.getLayer(layerId)) {
      map.setLayoutProperty(layerId, "text-field", labelField);
    }
  });
};

watch(showMarkerLabels, () => {
  applyMarkerLabelVisibility();
});

const persistMapView = () => {
  if (!mapInstance.value) {
    return;
  }
  const center = mapInstance.value.getCenter();
  mapSettingsStore.setMapView({
    lat: center.lat,
    lon: center.lng,
    zoom: mapInstance.value.getZoom()
  });
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

const handleClusterZoom = () => {
  if (!mapInstance.value || !mapReady.value) {
    return;
  }
  renderTelemetryMarkers();
  renderOperatorMarkers();
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
    markerSymbols.value.map(async (symbol) => {
      if (symbol.set === "napsg") {
        const symbolKey = buildMarkerSymbolKey(symbol.set, symbol.id);
        await loadMarkerImage(map, symbolKey, markerIconUrl(symbol.set, symbol.id), false);
        return;
      }
      const mdiName = symbol.mdi ?? symbol.id;
      const svg = await loadMdiSvg(mdiName);
      if (!svg) {
        console.warn(`Failed to load MDI icon ${mdiName} for symbol ${symbol.id}.`);
        return;
      }
      await loadMarkerImage(map, buildTelemetryIconId(symbol.id), svgToDataUrl(svg), true);
    })
  );
  markerImagesReady.value = true;
  telemetryIconsReady.value = true;
};

const buildOperatorFeatureCollection = () =>
  ({
    type: "FeatureCollection",
    features: markersStore.markers.filter((marker) => !marker.expired).map((marker) => {
      const override = dragPositions.value.get(marker.id);
      const lat = override?.lat ?? marker.lat;
      const lon = override?.lon ?? marker.lon;
      const resolvedSymbol = marker.symbol ? resolveTelemetryIconValue(marker.symbol, symbolKeySet.value) : "";
      const resolvedCategory = marker.category
        ? resolveTelemetryIconValue(marker.category, symbolKeySet.value)
        : "";
      const symbolInfo =
        getMarkerSymbol(resolvedSymbol || marker.symbol, marker.symbolSet ?? marker.category) ??
        getMarkerSymbol(resolvedCategory || marker.category, marker.symbolSet ?? marker.category);
      const mdiKey = symbolInfo?.set === "mdi" ? symbolInfo.id : undefined;
      const symbolKey = mdiKey
        ? buildTelemetryIconId(mdiKey)
        : symbolInfo?.set === "napsg"
          ? buildMarkerSymbolKey(symbolInfo.set, symbolInfo.id)
          : "marker-fallback";
      const iconScale = symbolInfo?.set === "napsg" ? NAPSG_ICON_SCALE : TELEMETRY_ICON_SCALE;
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
  if (!mapInstance.value || !mapReady.value) {
    return;
  }
  const map = mapInstance.value;
  const sourceId = "telemetry";
  const clusterLayerId = "telemetry-clusters";
  const clusterCountLayerId = "telemetry-cluster-count";
  const layerId = "telemetry-icons";
  const clusterRadius = resolveClusterRadius(map.getZoom());
  let existing = map.getSource(sourceId) as maplibregl.GeoJSONSource | undefined;
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
        icon: buildTelemetryIconId("person")
      }
    }))
  } as GeoJSON.FeatureCollection;

  if (existing) {
    existing.setData(featureCollection);
  }

  const clusterLayersMissing = !map.getLayer(clusterLayerId) || !map.getLayer(clusterCountLayerId);
  if (existing && telemetryClusterRadius !== clusterRadius) {
    if (map.getLayer(layerId)) {
      map.removeLayer(layerId);
    }
    if (map.getLayer(clusterCountLayerId)) {
      map.removeLayer(clusterCountLayerId);
    }
    if (map.getLayer(clusterLayerId)) {
      map.removeLayer(clusterLayerId);
    }
    map.removeSource(sourceId);
    existing = undefined;
  }

  if (!existing) {
    map.addSource(sourceId, {
      type: "geojson",
      data: featureCollection,
      cluster: true,
      clusterMaxZoom: TELEMETRY_CLUSTER_MAX_ZOOM,
      clusterRadius
    });
    telemetryClusterRadius = clusterRadius;
    map.addLayer({
      id: clusterLayerId,
      type: "circle",
      source: sourceId,
      filter: ["has", "point_count"],
      paint: {
        "circle-color": MARKER_CLUSTER_FILL_COLOR,
        "circle-radius": [
          "step",
          ["get", "point_count"],
          14,
          10,
          18,
          25,
          22
        ],
        "circle-opacity": MARKER_CLUSTER_FILL_OPACITY,
        "circle-stroke-color": MARKER_PRIMARY_COLOR,
        "circle-stroke-width": 2
      }
    });
    map.addLayer({
      id: clusterCountLayerId,
      type: "symbol",
      source: sourceId,
      filter: ["has", "point_count"],
      layout: {
        "text-field": "{point_count_abbreviated}",
        "text-font": ["Noto Sans Regular"],
        "text-size": 12,
        "text-allow-overlap": true,
        "text-ignore-placement": true
      },
      paint: {
        "text-color": "#FFFFFF"
      }
    });
  } else if (clusterLayersMissing) {
    if (!map.getLayer(clusterLayerId)) {
      map.addLayer({
        id: clusterLayerId,
        type: "circle",
        source: sourceId,
        filter: ["has", "point_count"],
        paint: {
          "circle-color": MARKER_CLUSTER_FILL_COLOR,
          "circle-radius": [
            "step",
            ["get", "point_count"],
            14,
            10,
            18,
            25,
            22
          ],
          "circle-opacity": MARKER_CLUSTER_FILL_OPACITY,
          "circle-stroke-color": MARKER_PRIMARY_COLOR,
          "circle-stroke-width": 2
        }
      });
    }
    if (!map.getLayer(clusterCountLayerId)) {
      map.addLayer({
        id: clusterCountLayerId,
        type: "symbol",
        source: sourceId,
        filter: ["has", "point_count"],
        layout: {
          "text-field": "{point_count_abbreviated}",
          "text-font": ["Noto Sans Regular"],
          "text-size": 12,
          "text-allow-overlap": true,
          "text-ignore-placement": true
        },
      paint: {
        "text-color": "#FFFFFF"
      }
    });
  }
  }

  if (telemetryIconsReady.value && !map.getLayer(layerId)) {
    map.addLayer({
      id: layerId,
      type: "symbol",
      source: sourceId,
      filter: ["!", ["has", "point_count"]],
      layout: {
        "icon-image": ["coalesce", ["image", ["get", "icon"]], ["image", "mdi-marker"]],
        "icon-size": buildTelemetryIconSizeExpression(map.getZoom()),
        "icon-allow-overlap": true,
        ...buildMarkerLabelLayout()
      },
      paint: {
        "icon-color": TELEMETRY_ICON_COLOR,
        "icon-halo-color": MARKER_PRIMARY_COLOR,
        "icon-halo-width": MARKER_ICON_HALO_WIDTH,
        ...markerLabelPaint
      }
    });
  }

  if (!telemetryInteractionReady) {
    map.on("click", clusterLayerId, (event) => {
      const feature = event.features?.[0];
      const clusterId = feature?.properties?.cluster_id;
      if (clusterId === undefined || clusterId === null) {
        return;
      }
      const source = map.getSource(sourceId) as maplibregl.GeoJSONSource | undefined;
      if (!source) {
        return;
      }
      source.getClusterExpansionZoom(Number(clusterId), (error, zoom) => {
        if (error) {
          return;
        }
        const geometry = feature?.geometry as GeoJSON.Point | undefined;
        const coordinates = geometry?.coordinates as [number, number] | undefined;
        if (!coordinates) {
          return;
        }
        map.easeTo({ center: coordinates, zoom });
      });
    });
    map.on("mouseenter", clusterLayerId, () => {
      map.getCanvas().style.cursor = "pointer";
    });
    map.on("mouseleave", clusterLayerId, () => {
      map.getCanvas().style.cursor = "";
    });
    map.on("move", () => {
      if (inspectorOpen.value && selected.value) {
        updateInspectorPosition(selected.value);
      }
    });
    telemetryInteractionReady = true;
  }

  if (!telemetryIconInteractionReady && telemetryIconsReady.value && map.getLayer(layerId)) {
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
    telemetryIconInteractionReady = true;
  }
};

const renderOperatorMarkers = () => {
  if (!mapInstance.value || !mapReady.value || !markerImagesReady.value) {
    return;
  }
  const map = mapInstance.value;
  const sourceId = "operator-markers";
  const clusterLayerId = "operator-marker-clusters";
  const clusterCountLayerId = "operator-marker-cluster-count";
  const layerId = "operator-marker-layer";
  const clusterRadius = resolveClusterRadius(map.getZoom());
  const featureCollection = buildOperatorFeatureCollection();
  let existing = map.getSource(sourceId) as maplibregl.GeoJSONSource | undefined;
  if (existing) {
    existing.setData(featureCollection);
  }

  const operatorClusterLayersMissing = !map.getLayer(clusterLayerId) || !map.getLayer(clusterCountLayerId);
  if (existing && operatorClusterRadius !== clusterRadius) {
    if (map.getLayer(layerId)) {
      map.removeLayer(layerId);
    }
    if (map.getLayer(clusterCountLayerId)) {
      map.removeLayer(clusterCountLayerId);
    }
    if (map.getLayer(clusterLayerId)) {
      map.removeLayer(clusterLayerId);
    }
    map.removeSource(sourceId);
    existing = undefined;
  }

  if (!existing) {
    map.addSource(sourceId, {
      type: "geojson",
      data: featureCollection,
      cluster: true,
      clusterMaxZoom: TELEMETRY_CLUSTER_MAX_ZOOM,
      clusterRadius
    });
    operatorClusterRadius = clusterRadius;
    map.addLayer({
      id: clusterLayerId,
      type: "circle",
      source: sourceId,
      filter: ["has", "point_count"],
      paint: {
        "circle-color": MARKER_CLUSTER_FILL_COLOR,
        "circle-radius": [
          "step",
          ["get", "point_count"],
          14,
          10,
          18,
          25,
          22
        ],
        "circle-opacity": MARKER_CLUSTER_FILL_OPACITY,
        "circle-stroke-color": MARKER_PRIMARY_COLOR,
        "circle-stroke-width": 2
      }
    });
    map.addLayer({
      id: clusterCountLayerId,
      type: "symbol",
      source: sourceId,
      filter: ["has", "point_count"],
      layout: {
        "text-field": "{point_count_abbreviated}",
        "text-font": ["Noto Sans Regular"],
        "text-size": 12,
        "text-allow-overlap": true,
        "text-ignore-placement": true
      },
      paint: {
        "text-color": "#FFFFFF"
      }
    });
    map.addLayer({
      id: layerId,
      type: "symbol",
      source: sourceId,
      filter: ["!", ["has", "point_count"]],
      layout: {
        "icon-image": ["coalesce", ["image", ["get", "symbol"]], ["image", "marker-fallback"]],
        "icon-size": buildIconSizeExpression(map.getZoom()),
        "icon-allow-overlap": true,
        ...buildMarkerLabelLayout()
      },
      paint: {
        "icon-color": ["coalesce", ["get", "color"], MARKER_ICON_COLOR],
        "icon-halo-color": MARKER_PRIMARY_COLOR,
        "icon-halo-width": MARKER_ICON_HALO_WIDTH,
        ...markerLabelPaint
      }
    });
  } else if (operatorClusterLayersMissing) {
    if (!map.getLayer(clusterLayerId)) {
      map.addLayer({
        id: clusterLayerId,
        type: "circle",
        source: sourceId,
        filter: ["has", "point_count"],
        paint: {
          "circle-color": MARKER_CLUSTER_FILL_COLOR,
          "circle-radius": [
            "step",
            ["get", "point_count"],
            14,
            10,
            18,
            25,
            22
          ],
          "circle-opacity": MARKER_CLUSTER_FILL_OPACITY,
          "circle-stroke-color": MARKER_PRIMARY_COLOR,
          "circle-stroke-width": 2
        }
      });
    }
    if (!map.getLayer(clusterCountLayerId)) {
      map.addLayer({
        id: clusterCountLayerId,
        type: "symbol",
        source: sourceId,
        filter: ["has", "point_count"],
        layout: {
          "text-field": "{point_count_abbreviated}",
          "text-font": ["Noto Sans Regular"],
          "text-size": 12,
          "text-allow-overlap": true,
          "text-ignore-placement": true
        },
      paint: {
        "text-color": "#FFFFFF"
      }
    });
    }
  }

  if (!map.getLayer(layerId)) {
    map.addLayer({
      id: layerId,
      type: "symbol",
      source: sourceId,
      filter: ["!", ["has", "point_count"]],
      layout: {
        "icon-image": ["coalesce", ["image", ["get", "symbol"]], ["image", "marker-fallback"]],
        "icon-size": buildIconSizeExpression(map.getZoom()),
        "icon-allow-overlap": true,
        ...buildMarkerLabelLayout()
      },
      paint: {
        "icon-color": ["coalesce", ["get", "color"], MARKER_ICON_COLOR],
        "icon-halo-color": MARKER_PRIMARY_COLOR,
        "icon-halo-width": MARKER_ICON_HALO_WIDTH,
        ...markerLabelPaint
      }
    });
  }

  handleMarkerZoom();

  if (!markerInteractionReady) {
    map.on("mousedown", layerId, startMarkerDrag);
    map.on("zoom", handleMarkerZoom);
    map.on("click", clusterLayerId, (event) => {
      const feature = event.features?.[0];
      const clusterId = feature?.properties?.cluster_id;
      if (clusterId === undefined || clusterId === null) {
        return;
      }
      const source = map.getSource(sourceId) as maplibregl.GeoJSONSource | undefined;
      if (!source) {
        return;
      }
      source.getClusterExpansionZoom(Number(clusterId), (error, zoom) => {
        if (error) {
          return;
        }
        const geometry = feature?.geometry as GeoJSON.Point | undefined;
        const coordinates = geometry?.coordinates as [number, number] | undefined;
        if (!coordinates) {
          return;
        }
        map.easeTo({ center: coordinates, zoom });
      });
    });
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
    map.on("mouseenter", clusterLayerId, () => {
      if (!draggingMarkerId.value) {
        map.getCanvas().style.cursor = "pointer";
      }
    });
    map.on("mouseleave", clusterLayerId, () => {
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
  applyMarkerLabelVisibility();
};

const loadMarkerSymbols = async () => {
  try {
    await markersStore.fetchMarkerSymbols();
  } catch (error) {
    console.warn("Failed to load marker symbols.", error);
  } finally {
    ensureMarkerSelection();
  }
};

onMounted(async () => {
  const symbolsPromise = loadMarkerSymbols();
  if (mapContainer.value) {
    const initialView = mapView.value ?? defaultMapView;
    mapCoordinates.value = { lat: initialView.lat, lon: initialView.lon };
    mapInstance.value = new maplibregl.Map({
      container: mapContainer.value,
      style: mapStyle,
      center: [initialView.lon, initialView.lat],
      zoom: initialView.zoom
    });
    mapInstance.value.on("load", async () => {
      mapReady.value = true;
      await symbolsPromise;
      await loadMarkerImages();
      renderMarkers();
      mapInstance.value?.on("click", handleMapClick);
      mapInstance.value?.on("mousemove", handleMapPointerMove);
      mapInstance.value?.on("mouseleave", handleMapPointerLeave);
      mapInstance.value?.on("zoomend", handleClusterZoom);
      mapInstance.value?.on("moveend", persistMapView);
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
    mapInstance.value.off("zoomend", handleClusterZoom);
    mapInstance.value.off("zoom", handleMarkerZoom);
    mapInstance.value.off("moveend", persistMapView);
    mapInstance.value.off("mousemove", handleMapPointerMove);
    mapInstance.value.off("mouseleave", handleMapPointerLeave);
  }
  window.removeEventListener("resize", handleInspectorViewportChange);
  window.removeEventListener("scroll", handleInspectorViewportChange);
  stopDrag();
  stopMarkerDrag();
});
</script>
