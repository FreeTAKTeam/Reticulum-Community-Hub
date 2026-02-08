<template>
  <div class="webmap-cosmos" :class="{ 'webmap-cosmos--sidebar-collapsed': markersPanelCollapsed }">
    <section class="webmap-main">
      <div class="webmap-stage">
        <LoadingSkeleton v-if="telemetry.loading && !mapReady" class="webmap-loader" />
        <div ref="mapContainer" class="webmap-canvas"></div>

        <div ref="markerToolbarRef" class="webmap-toolbar">
          <div class="webmap-toolbar-row">
            <button
              type="button"
              class="webmap-marker-trigger"
              :aria-expanded="markerToolbarOpen"
              aria-haspopup="menu"
              @click="toggleMarkerToolbar"
            >
              <span class="webmap-marker-trigger-icon">
                <img v-if="selectedMarkerIconUrl" :src="selectedMarkerIconUrl" :alt="selectedMarkerLabel" />
              </span>
              <span class="webmap-marker-trigger-label">{{ selectedMarkerLabel }}</span>
              <span class="webmap-marker-trigger-arrow" :class="{ open: markerToolbarOpen }" aria-hidden="true">
                <svg viewBox="0 0 24 24">
                  <path d="M7 10l5 5 5-5" />
                </svg>
              </span>
            </button>
            <button
              type="button"
              class="webmap-place-btn"
              :class="{ active: markerMode }"
              @click="toggleMarkerMode"
            >
              <span class="webmap-place-btn-icon" aria-hidden="true">+</span>
              <span>{{ markerMode ? "Placement Armed" : "Place Marker" }}</span>
            </button>
            <div class="webmap-place-hint" :class="{ active: markerMode }">{{ markerHintText }}</div>
          </div>

          <div v-if="markerToolbarOpen" class="webmap-marker-menu cui-scrollbar" role="menu">
            <button
              v-for="symbol in markerCatalog"
              :key="symbol.id"
              type="button"
              class="webmap-marker-option"
              :class="{ active: markerCategory === symbol.id }"
              @click="selectMarkerSymbol(symbol.id)"
            >
              <span class="webmap-marker-option-main">
                <span class="webmap-marker-option-icon">
                  <img :src="markerCatalogIconUrl(symbol.id)" :alt="symbol.label" />
                </span>
                <span class="webmap-marker-option-name">{{ symbol.label }}</span>
              </span>
            </button>
          </div>
        </div>

        <div
          v-if="markerRenameOpen"
          class="webmap-rename-popover"
          :style="markerRenameStyle"
          @click.stop
          @contextmenu.prevent
        >
          <div class="webmap-rename-title">Edit Marker Name</div>
          <input
            v-model="markerRenameValue"
            class="webmap-rename-input"
            type="text"
            maxlength="96"
            placeholder="Marker name"
            @keydown.enter.prevent="submitMarkerRename"
            @keydown.esc.prevent="closeMarkerRename"
          />
          <div class="webmap-rename-actions">
            <button type="button" class="webmap-rename-btn" @click="closeMarkerRename">Cancel</button>
            <button type="button" class="webmap-rename-btn webmap-rename-btn--primary" @click="submitMarkerRename">
              {{ markerRenameBusy ? "Saving..." : "Save" }}
            </button>
          </div>
        </div>

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
    </section>

    <aside
      class="webmap-sidebar"
      :class="{ 'webmap-sidebar--collapsed': markersPanelCollapsed }"
    >
      <div class="webmap-sidebar-head">
        <div v-if="!markersPanelCollapsed" class="webmap-sidebar-title">Marker Registry</div>
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

      <div v-if="markersPanelCollapsed" class="webmap-sidebar-collapsed">Markers</div>

      <div v-else class="webmap-sidebar-body">
        <div class="webmap-filters">
          <BaseInput v-model="topicFilter" label="Topic ID" />
          <BaseInput v-model="search" label="Search Identity" />
          <BaseButton variant="secondary" icon-left="filter" @click="applyFilters">Apply</BaseButton>
        </div>

        <div class="cui-tab-group webmap-tabs">
          <BaseButton
            variant="tab"
            size="sm"
            :class="{ 'cui-tab-active': activeMarkerTab === 'operator' }"
            @click="activeMarkerTab = 'operator'"
          >
            Operator
          </BaseButton>
          <BaseButton
            variant="tab"
            size="sm"
            :class="{ 'cui-tab-active': activeMarkerTab === 'telemetry' }"
            @click="activeMarkerTab = 'telemetry'"
          >
            Telemetry
          </BaseButton>
        </div>

        <div v-if="activeMarkerTab === 'operator'" class="webmap-list-wrap cui-scrollbar">
          <LoadingSkeleton v-if="markersStore.loading" />
          <ul v-else class="webmap-list">
            <li
              v-for="marker in operatorPagination.items"
              :key="marker.id"
              class="webmap-list-item"
              :class="{ 'webmap-list-item--expired': marker.expired }"
              @click="focusOperatorMarker(marker)"
            >
              <div class="webmap-list-name">{{ marker.name }}</div>
              <div class="webmap-list-meta">
                {{ marker.category }} · {{ marker.lat.toFixed(4) }}, {{ marker.lon.toFixed(4) }}
              </div>
            </li>
          </ul>
        </div>

        <div v-else class="webmap-list-wrap cui-scrollbar">
          <LoadingSkeleton v-if="telemetry.loading" />
          <ul v-else class="webmap-list">
            <li
              v-for="marker in telemetryPagination.items"
              :key="marker.id"
              class="webmap-list-item"
              @click="selectMarker(marker)"
            >
              <div class="webmap-list-name">{{ marker.name }}</div>
              <div class="webmap-list-meta">{{ marker.lat.toFixed(4) }}, {{ marker.lon.toFixed(4) }}</div>
            </li>
          </ul>
        </div>

        <div v-if="activeMarkerTab === 'operator'" class="webmap-pagination">
          <span v-if="operatorPagination.total">
            {{ operatorPagination.startIndex }}-{{ operatorPagination.endIndex }} / {{ operatorPagination.total }}
          </span>
          <span v-else>No markers yet.</span>
          <div class="webmap-pagination-actions">
            <BaseButton
              variant="secondary"
              size="sm"
              icon-left="chevron-left"
              :disabled="operatorPagination.page <= 1"
              @click="updateOperatorPage(-1)"
            >
              Prev
            </BaseButton>
            <BaseButton
              variant="secondary"
              size="sm"
              icon-left="chevron-right"
              :disabled="operatorPagination.page >= operatorPagination.totalPages"
              @click="updateOperatorPage(1)"
            >
              Next
            </BaseButton>
          </div>
        </div>

        <div v-else class="webmap-pagination">
          <span v-if="telemetryPagination.total">
            {{ telemetryPagination.startIndex }}-{{ telemetryPagination.endIndex }} / {{ telemetryPagination.total }}
          </span>
          <span v-else>No telemetry markers yet.</span>
          <div class="webmap-pagination-actions">
            <BaseButton
              variant="secondary"
              size="sm"
              icon-left="chevron-left"
              :disabled="telemetryPagination.page <= 1"
              @click="updateTelemetryPage(-1)"
            >
              Prev
            </BaseButton>
            <BaseButton
              variant="secondary"
              size="sm"
              icon-left="chevron-right"
              :disabled="telemetryPagination.page >= telemetryPagination.totalPages"
              @click="updateTelemetryPage(1)"
            >
              Next
            </BaseButton>
          </div>
        </div>
      </div>
    </aside>

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
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, watch } from "vue";
import { ref } from "vue";
import { storeToRefs } from "pinia";
import maplibregl from "maplibre-gl";
import BaseButton from "../components/BaseButton.vue";
import BaseFormattedOutput from "../components/BaseFormattedOutput.vue";
import BaseInput from "../components/BaseInput.vue";
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
const markerToolbarRef = ref<HTMLDivElement | null>(null);
const markerToolbarOpen = ref(false);
const selectedMarkerIconUrl = ref("");
const markerCatalogIconUrls = ref<Record<string, string>>({});
const markerCategory = ref<string>("marker");
const symbolKeySet = computed(
  () => new Set(markerSymbols.value.filter((symbol) => symbol.set !== "napsg").map((symbol) => symbol.id))
);
const markerRenameOpen = ref(false);
const markerRenameMarkerId = ref("");
const markerRenameValue = ref("");
const markerRenamePosition = ref({ left: 12, top: 12 });
const markerRenameBusy = ref(false);
const creatingMarker = ref(false);
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
};
const markerCatalog = computed(() =>
  markerSymbols.value.map((symbol) => ({
    id: symbol.id,
    label: symbol.label,
    set: symbol.set,
    mdi: symbol.mdi,
    color: symbol.color
  }))
);
const selectedMarkerLabel = computed(() => {
  const selectedSymbol = markerCatalog.value.find((symbol) => symbol.id === markerCategory.value);
  return selectedSymbol?.label ?? "Marker";
});
const markerHintText = computed(() =>
  markerMode.value ? "Click map to create marker" : "Select marker type and arm placement"
);
const markerRenameStyle = computed(() => ({
  left: `${markerRenamePosition.value.left}px`,
  top: `${markerRenamePosition.value.top}px`
}));
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
  markerToolbarOpen.value = false;
  markerMode.value = !markerMode.value;
};

const toggleMarkerToolbar = () => {
  markerToolbarOpen.value = !markerToolbarOpen.value;
};

const selectMarkerSymbol = (symbolId: string) => {
  markerCategory.value = symbolId;
  markerMode.value = true;
  markerToolbarOpen.value = false;
};

const closeMarkerRename = () => {
  markerRenameOpen.value = false;
  markerRenameMarkerId.value = "";
  markerRenameValue.value = "";
  markerRenameBusy.value = false;
};

const openMarkerRename = (markerId: string, point: { x: number; y: number }) => {
  const marker = markersStore.markerIndex.get(markerId);
  const container = mapContainer.value;
  if (!marker || !container) {
    closeMarkerRename();
    return;
  }
  const width = 260;
  const height = 140;
  const left = Math.min(Math.max(point.x + 12, 12), Math.max(12, container.clientWidth - width - 12));
  const top = Math.min(Math.max(point.y + 12, 12), Math.max(12, container.clientHeight - height - 12));
  markerRenameMarkerId.value = markerId;
  markerRenameValue.value = marker.name;
  markerRenamePosition.value = { left, top };
  markerRenameOpen.value = true;
};

const submitMarkerRename = async () => {
  const markerId = markerRenameMarkerId.value;
  const nextName = markerRenameValue.value.trim();
  if (!markerId || !nextName || markerRenameBusy.value) {
    return;
  }
  markerRenameBusy.value = true;
  try {
    await markersStore.updateMarkerName(markerId, nextName);
    renderOperatorMarkers();
    closeMarkerRename();
  } finally {
    markerRenameBusy.value = false;
  }
};

const createMarkerAt = async (lngLat: maplibregl.LngLat) => {
  if (creatingMarker.value) {
    return;
  }
  creatingMarker.value = true;
  const symbolId = markerCategory.value;
  try {
    await markersStore.createMarker({
      name: defaultMarkerName(symbolId),
      type: symbolId,
      symbol: symbolId,
      category: symbolId,
      lat: lngLat.lat,
      lon: lngLat.lng
    });
    renderOperatorMarkers();
    markerMode.value = false;
  } finally {
    creatingMarker.value = false;
  }
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

const pointHitsRenderedLayer = (
  point: { x: number; y: number },
  layerIds: string[]
) => {
  const map = mapInstance.value;
  if (!map) {
    return false;
  }
  const existingLayers = layerIds.filter((layerId) => Boolean(map.getLayer(layerId)));
  if (!existingLayers.length) {
    return false;
  }
  return map.queryRenderedFeatures(point, { layers: existingLayers }).length > 0;
};

const handleDocumentPointerDown = (event: MouseEvent) => {
  if (!markerToolbarOpen.value || !markerToolbarRef.value) {
    return;
  }
  const target = event.target as Node | null;
  if (!target || markerToolbarRef.value.contains(target)) {
    return;
  }
  markerToolbarOpen.value = false;
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

const focusOperatorMarker = (marker: { lat: number; lon: number }) => {
  if (!mapInstance.value) {
    return;
  }
  mapInstance.value.flyTo({ center: [marker.lon, marker.lat], zoom: 9 });
};

const handleMapClick = (event: maplibregl.MapMouseEvent) => {
  markerToolbarOpen.value = false;
  if (markerRenameOpen.value) {
    closeMarkerRename();
  }
  if (!markerMode.value) {
    return;
  }
  if (
    pointHitsRenderedLayer(event.point, [
      "operator-marker-layer",
      "operator-marker-clusters",
      "operator-marker-cluster-count",
      "telemetry-icons",
      "telemetry-clusters",
      "telemetry-cluster-count"
    ])
  ) {
    return;
  }
  void createMarkerAt(event.lngLat);
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

watch(markerCategory, () => {
  void refreshSelectedMarkerIcon();
});

watch(
  () =>
    markerCatalog.value
      .map((symbol) => `${symbol.id}:${symbol.set}:${symbol.mdi ?? ""}:${symbol.color ?? ""}`)
      .join("|"),
  () => {
    ensureMarkerSelection();
    void refreshMarkerCatalogIcons();
    void refreshSelectedMarkerIcon();
  }
);

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
const MARKER_UI_ICON_COLOR_FALLBACK = "#74f7ff";
const HEX_COLOR = /^#(?:[0-9a-f]{3}|[0-9a-f]{6})$/i;
const normalizeIconColor = (value?: string) =>
  value && HEX_COLOR.test(value) ? value : MARKER_UI_ICON_COLOR_FALLBACK;
const svgToUiIconDataUrl = (svg: string, color?: string) => {
  const resolvedColor = normalizeIconColor(color);
  const tintedSvg = svg.replace(/<svg\b([^>]*)>/i, (_match, attrs: string) => {
    if (/\sfill\s*=\s*"[^"]*"/i.test(attrs)) {
      return `<svg${attrs.replace(/\sfill\s*=\s*"[^"]*"/i, ` fill="${resolvedColor}"`)}>`;
    }
    return `<svg${attrs} fill="${resolvedColor}">`;
  });
  return svgToDataUrl(tintedSvg);
};

const markerCatalogIconUrl = (symbolId: string) => {
  return markerCatalogIconUrls.value[symbolId] ?? markerFallbackUrl;
};

const refreshMarkerCatalogIcons = async () => {
  const entries = await Promise.all(
    markerCatalog.value.map(async (symbol) => {
      if (symbol.set === "napsg") {
        return [symbol.id, markerIconUrl(symbol.set, symbol.id)] as const;
      }
      const mdiName = symbol.mdi ?? symbol.id;
      const svg = await loadMdiSvg(mdiName);
      return [symbol.id, svg ? svgToUiIconDataUrl(svg, symbol.color) : markerFallbackUrl] as const;
    })
  );
  markerCatalogIconUrls.value = Object.fromEntries(entries);
};

const refreshSelectedMarkerIcon = async () => {
  const existing = markerCatalogIconUrls.value[markerCategory.value];
  if (existing) {
    selectedMarkerIconUrl.value = existing;
    return;
  }
  const symbol = getMarkerSymbol(markerCategory.value, markerCategory.value);
  if (symbol?.set === "napsg") {
    selectedMarkerIconUrl.value = markerIconUrl(symbol.set, symbol.id);
    return;
  }
  const mdiName = symbol?.mdi ?? symbol?.id ?? markerCategory.value;
  const svg = await loadMdiSvg(mdiName);
  selectedMarkerIconUrl.value = svg ? svgToUiIconDataUrl(svg, symbol?.color) : markerFallbackUrl;
};

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
  if (!mapInstance.value) {
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

const handleOperatorMarkerContextMenu = (event: maplibregl.MapMouseEvent & maplibregl.EventData) => {
  const feature = event.features?.[0];
  const markerId = feature?.properties?.id;
  if (!markerId) {
    return;
  }
  event.preventDefault();
  (event.originalEvent as MouseEvent | undefined)?.preventDefault?.();
  openMarkerRename(String(markerId), event.point);
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
    map.on("contextmenu", layerId, handleOperatorMarkerContextMenu);
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
    void refreshMarkerCatalogIcons();
    void refreshSelectedMarkerIcon();
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
  window.addEventListener("mousedown", handleDocumentPointerDown);
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
    mapInstance.value.off("click", handleMapClick);
    mapInstance.value.off("mousemove", handleMapPointerMove);
    mapInstance.value.off("mouseleave", handleMapPointerLeave);
  }
  window.removeEventListener("resize", handleInspectorViewportChange);
  window.removeEventListener("scroll", handleInspectorViewportChange);
  window.removeEventListener("mousedown", handleDocumentPointerDown);
  stopDrag();
  stopMarkerDrag();
});
</script>
<style scoped>
.webmap-cosmos {
  --wm-neon: #3bf4ff;
  --wm-neon-soft: rgba(59, 244, 255, 0.24);
  --wm-panel: rgba(4, 14, 24, 0.92);
  --wm-panel-alt: rgba(7, 22, 36, 0.9);
  --wm-amber: #ffb35c;
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(320px, 420px);
  gap: 14px;
  min-height: 0;
  color: #e2fcff;
  font-family: "Orbitron", "Rajdhani", "Barlow", sans-serif;
}

.webmap-cosmos--sidebar-collapsed {
  grid-template-columns: minmax(0, 1fr);
}

.webmap-main {
  min-width: 0;
}

.webmap-stage {
  position: relative;
  height: clamp(520px, 74vh, 860px);
  border-radius: 18px;
  border: 1px solid rgba(59, 244, 255, 0.26);
  background: linear-gradient(160deg, rgba(5, 16, 28, 0.96), rgba(2, 8, 14, 0.98));
  box-shadow:
    0 22px 54px rgba(1, 5, 12, 0.56),
    inset 0 0 0 1px rgba(59, 244, 255, 0.08);
  overflow: hidden;
}

.webmap-stage::before {
  content: "";
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at 1px 1px, rgba(59, 244, 255, 0.07) 1px, transparent 0) 0 0 / 18px 18px,
    linear-gradient(180deg, rgba(44, 188, 242, 0.12), transparent 42%);
  pointer-events: none;
  z-index: 1;
}

.webmap-canvas {
  width: 100%;
  height: 100%;
}

.webmap-loader {
  position: absolute;
  inset: 24px;
  z-index: 5;
}

.webmap-toolbar {
  position: absolute;
  top: 12px;
  left: 12px;
  right: 12px;
  z-index: 6;
  display: grid;
  gap: 8px;
  pointer-events: none;
}

.webmap-toolbar > * {
  pointer-events: auto;
}

.webmap-toolbar-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.webmap-marker-trigger {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  min-height: 46px;
  padding: 0 12px;
  border-radius: 999px;
  border: 1px solid rgba(59, 244, 255, 0.35);
  background: linear-gradient(180deg, rgba(8, 24, 38, 0.96), rgba(6, 16, 26, 0.94));
  color: #dcfdff;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  font-size: 11px;
  box-shadow: 0 0 14px rgba(59, 244, 255, 0.12);
}

.webmap-marker-trigger-icon {
  width: 26px;
  height: 26px;
  border-radius: 999px;
  border: 1px solid rgba(59, 244, 255, 0.55);
  background: radial-gradient(circle at 30% 30%, rgba(59, 244, 255, 0.2), rgba(7, 20, 31, 0.88));
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.webmap-marker-trigger-icon img {
  width: 16px;
  height: 16px;
  object-fit: contain;
  filter: drop-shadow(0 0 8px rgba(59, 244, 255, 0.55));
}

.webmap-marker-trigger-label {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.webmap-marker-trigger-arrow {
  width: 18px;
  height: 18px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: transform 160ms ease;
}

.webmap-marker-trigger-arrow svg {
  width: 14px;
  height: 14px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.webmap-marker-trigger-arrow.open {
  transform: rotate(180deg);
}

.webmap-place-btn {
  min-height: 46px;
  padding: 0 14px;
  border-radius: 10px;
  border: 1px solid rgba(59, 244, 255, 0.3);
  background: linear-gradient(180deg, rgba(9, 24, 37, 0.96), rgba(6, 15, 25, 0.95));
  color: #d8fbff;
  display: inline-flex;
  align-items: center;
  gap: 10px;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  font-size: 11px;
}

.webmap-place-btn-icon {
  font-size: 16px;
  line-height: 1;
}

.webmap-place-btn.active {
  border-color: rgba(255, 179, 92, 0.62);
  box-shadow:
    0 0 16px rgba(255, 179, 92, 0.2),
    inset 0 0 12px rgba(255, 179, 92, 0.2);
  color: #ffe0bf;
}

.webmap-place-hint {
  min-height: 46px;
  padding: 0 12px;
  border-radius: 10px;
  border: 1px dashed rgba(59, 244, 255, 0.22);
  background: rgba(7, 18, 30, 0.85);
  display: inline-flex;
  align-items: center;
  color: rgba(214, 251, 255, 0.62);
  text-transform: uppercase;
  letter-spacing: 0.14em;
  font-size: 10px;
}

.webmap-place-hint.active {
  color: rgba(255, 215, 170, 0.9);
  border-color: rgba(255, 179, 92, 0.55);
}

.webmap-marker-menu {
  max-height: 300px;
  overflow-y: auto;
  padding: 8px;
  width: min(420px, 100%);
  border-radius: 12px;
  border: 1px solid rgba(59, 244, 255, 0.28);
  background: linear-gradient(180deg, rgba(6, 18, 30, 0.98), rgba(4, 12, 22, 0.98));
  box-shadow: 0 20px 34px rgba(0, 0, 0, 0.42);
}

.webmap-marker-option {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 10px;
  border-radius: 9px;
  border: 1px solid rgba(59, 244, 255, 0.18);
  background: rgba(7, 18, 30, 0.66);
  color: #dcfdff;
  padding: 8px 10px;
}

.webmap-marker-option-main {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.webmap-marker-option-icon {
  width: 22px;
  height: 22px;
  border-radius: 999px;
  border: 1px solid rgba(59, 244, 255, 0.55);
  background: radial-gradient(circle at 30% 30%, rgba(59, 244, 255, 0.2), rgba(7, 20, 31, 0.88));
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.webmap-marker-option-icon img {
  width: 15px;
  height: 15px;
  object-fit: contain;
  filter: drop-shadow(0 0 7px rgba(59, 244, 255, 0.55));
}

.webmap-marker-option + .webmap-marker-option {
  margin-top: 6px;
}

.webmap-marker-option.active {
  border-color: rgba(59, 244, 255, 0.56);
  background: rgba(59, 244, 255, 0.13);
}

.webmap-marker-option-name {
  text-transform: uppercase;
  letter-spacing: 0.11em;
  font-size: 11px;
}

.webmap-rename-popover {
  position: absolute;
  z-index: 7;
  width: 260px;
  padding: 10px;
  border-radius: 10px;
  border: 1px solid rgba(59, 244, 255, 0.35);
  background: linear-gradient(180deg, rgba(9, 26, 39, 0.98), rgba(7, 18, 30, 0.98));
  box-shadow: 0 14px 30px rgba(0, 0, 0, 0.45);
}

.webmap-rename-title {
  margin-bottom: 8px;
  text-transform: uppercase;
  letter-spacing: 0.16em;
  font-size: 10px;
  color: rgba(220, 251, 255, 0.7);
}

.webmap-rename-input {
  width: 100%;
  border-radius: 8px;
  border: 1px solid rgba(59, 244, 255, 0.3);
  background: rgba(6, 15, 25, 0.9);
  color: #e6feff;
  font-size: 12px;
  letter-spacing: 0.06em;
  padding: 8px 10px;
}

.webmap-rename-input:focus {
  outline: none;
  border-color: rgba(59, 244, 255, 0.64);
  box-shadow: 0 0 12px rgba(59, 244, 255, 0.22);
}

.webmap-rename-actions {
  margin-top: 8px;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.webmap-rename-btn {
  border-radius: 8px;
  border: 1px solid rgba(59, 244, 255, 0.28);
  background: rgba(7, 18, 30, 0.9);
  color: rgba(218, 251, 255, 0.9);
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.13em;
  padding: 6px 10px;
}

.webmap-rename-btn--primary {
  border-color: rgba(255, 179, 92, 0.52);
  color: #ffdcb8;
}

.webmap-sidebar {
  min-width: 0;
  display: flex;
  flex-direction: column;
  padding: 12px;
  border-radius: 16px;
  border: 1px solid rgba(59, 244, 255, 0.24);
  background: linear-gradient(180deg, var(--wm-panel), var(--wm-panel-alt));
  box-shadow: inset 0 0 18px rgba(5, 14, 24, 0.9);
}

.webmap-sidebar--collapsed {
  width: 58px;
  padding: 8px;
}

.webmap-cosmos--sidebar-collapsed .webmap-sidebar--collapsed {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  z-index: 8;
}

.webmap-sidebar-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.webmap-sidebar-title {
  font-size: 12px;
  letter-spacing: 0.2em;
  text-transform: uppercase;
}

.webmap-sidebar-collapsed {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  writing-mode: vertical-rl;
  text-orientation: mixed;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  font-size: 10px;
  color: rgba(214, 251, 255, 0.62);
}

.webmap-sidebar-body {
  margin-top: 10px;
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr) auto;
  gap: 10px;
  min-height: 0;
}

.webmap-filters {
  display: grid;
  gap: 8px;
}

.webmap-tabs {
  width: fit-content;
}

.webmap-list-wrap {
  min-height: 0;
  overflow-y: auto;
  padding-right: 4px;
}

.webmap-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 8px;
}

.webmap-list-item {
  border-radius: 10px;
  border: 1px solid rgba(59, 244, 255, 0.18);
  background: rgba(7, 18, 29, 0.75);
  padding: 9px 10px;
  cursor: pointer;
}

.webmap-list-item:hover {
  border-color: rgba(59, 244, 255, 0.46);
}

.webmap-list-item--expired {
  opacity: 0.56;
  text-decoration: line-through;
}

.webmap-list-name {
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.webmap-list-meta {
  margin-top: 4px;
  font-size: 10px;
  color: rgba(206, 248, 255, 0.62);
}

.webmap-pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  font-size: 10px;
  color: rgba(214, 251, 255, 0.64);
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.webmap-pagination-actions {
  display: inline-flex;
  gap: 6px;
}

:deep(.webmap-canvas .maplibregl-canvas) {
  outline: none;
}

@media (max-width: 1280px) {
  .webmap-cosmos {
    grid-template-columns: 1fr;
  }

  .webmap-sidebar--collapsed {
    width: 100%;
    min-height: 54px;
  }

  .webmap-sidebar-collapsed {
    writing-mode: horizontal-tb;
    text-orientation: mixed;
  }
}

@media (max-width: 860px) {
  .webmap-toolbar-row {
    align-items: stretch;
  }

  .webmap-place-hint {
    width: 100%;
  }

  .webmap-marker-trigger {
    flex: 1;
    min-width: 0;
  }
}
</style>
