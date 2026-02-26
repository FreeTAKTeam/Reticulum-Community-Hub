<template>
  <div class="webmap-cosmos" :class="{ 'webmap-cosmos--sidebar-collapsed': markersPanelCollapsed }">
    <section class="webmap-main">
      <div class="webmap-stage">
        <LoadingSkeleton v-if="telemetry.loading && !mapReady" class="webmap-loader" />
        <div ref="mapContainer" class="webmap-canvas"></div>

        <div class="webmap-marker-overlay-layer">
          <div v-if="markerReticleStyle" class="webmap-marker-reticle" :style="markerReticleStyle" aria-hidden="true">
            <span class="webmap-marker-reticle-corner webmap-marker-reticle-corner--tl"></span>
            <span class="webmap-marker-reticle-corner webmap-marker-reticle-corner--tr"></span>
            <span class="webmap-marker-reticle-corner webmap-marker-reticle-corner--bl"></span>
            <span class="webmap-marker-reticle-corner webmap-marker-reticle-corner--br"></span>
            <div class="webmap-marker-reticle-ring webmap-marker-reticle-ring--outer"></div>
            <div class="webmap-marker-reticle-ring webmap-marker-reticle-ring--inner"></div>
            <div class="webmap-marker-reticle-core">
              <div class="webmap-marker-reticle-name">{{ markerReticleLabel }}</div>
              <div class="webmap-marker-reticle-sub">{{ markerReticleSubLabel }}</div>
            </div>
          </div>

          <div
            v-if="markerCompassStyle"
            class="webmap-marker-compass"
            :style="markerCompassStyle"
            aria-hidden="true"
          >
            <svg viewBox="0 0 320 320">
              <circle class="webmap-marker-compass-orbit" cx="160" cy="160" r="146" />
              <circle class="webmap-marker-compass-inner-orbit" cx="160" cy="160" r="118" />
              <line
                v-for="tick in markerCompassTicks"
                :key="`tick-${tick.id}`"
                class="webmap-marker-compass-tick"
                :class="{ 'webmap-marker-compass-tick--major': tick.major }"
                :x1="tick.x1"
                :y1="tick.y1"
                :x2="tick.x2"
                :y2="tick.y2"
              />
              <text
                v-for="label in markerCompassLabels"
                :key="`label-${label.id}`"
                class="webmap-marker-compass-label"
                :x="label.x"
                :y="label.y"
              >
                {{ label.text }}
              </text>
              <line class="webmap-marker-compass-needle webmap-marker-compass-needle--north" x1="160" y1="160" x2="160" y2="34" />
              <line class="webmap-marker-compass-needle" x1="160" y1="160" x2="160" y2="286" />
              <line class="webmap-marker-compass-axis" x1="56" y1="160" x2="264" y2="160" />
              <line class="webmap-marker-compass-axis" x1="160" y1="56" x2="160" y2="264" />
              <circle class="webmap-marker-compass-hub" cx="160" cy="160" r="10" />
            </svg>
          </div>
        </div>

        <div
          v-if="markerRadialMenuStyle && markerRadialMenuItems.length"
          ref="markerRadialMenuRef"
          class="webmap-marker-radial-menu"
          :style="markerRadialMenuStyle"
          role="menu"
          @mousedown.stop
          @click.stop
          @contextmenu.prevent="dismissRadialMenus"
        >
          <button
            v-for="(item, index) in markerRadialMenuItems"
            :key="item.id"
            type="button"
            class="webmap-marker-radial-item"
            :class="{ 'webmap-marker-radial-item--danger': item.action === 'delete' }"
            :style="markerRadialMenuItemStyle(index, markerRadialMenuItems.length)"
            :title="item.label"
            @click.stop="handleMarkerRadialMenuItem(item)"
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path
                v-for="(segment, segmentIndex) in markerRadialIconPaths(item.icon)"
                :key="`${item.id}-${segmentIndex}`"
                :d="segment"
              />
            </svg>
            <span>{{ item.label }}</span>
          </button>
          <button
            type="button"
            class="webmap-marker-radial-center"
            :title="markerRadialMenuCenterLabel"
            @click.stop="handleMarkerRadialMenuCenter"
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path
                v-for="(segment, segmentIndex) in markerRadialIconPaths(markerRadialMenuCenterIcon)"
                :key="`center-${segmentIndex}`"
                :d="segment"
              />
            </svg>
            <span>{{ markerRadialMenuCenterLabel }}</span>
          </button>
        </div>
        <div
          v-if="zoneRadialMenuStyle && zoneRadialMenuZoneId"
          ref="zoneRadialMenuRef"
          class="webmap-marker-radial-menu webmap-zone-radial-menu"
          :style="zoneRadialMenuStyle"
          role="menu"
          @mousedown.stop
          @click.stop
          @contextmenu.prevent="dismissRadialMenus"
        >
          <button
            v-for="(item, index) in zoneRadialMenuItems"
            :key="item.id"
            type="button"
            class="webmap-marker-radial-item"
            :class="{ 'webmap-marker-radial-item--danger': item.action === 'delete' }"
            :style="markerRadialMenuItemStyle(index, zoneRadialMenuItems.length)"
            :title="item.label"
            @click.stop="handleZoneRadialMenuItem(item)"
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path
                v-for="(segment, segmentIndex) in markerRadialIconPaths(item.icon)"
                :key="`${item.id}-${segmentIndex}`"
                :d="segment"
              />
            </svg>
            <span>{{ item.label }}</span>
          </button>
          <button
            type="button"
            class="webmap-marker-radial-center"
            title="Close"
            @click.stop="closeZoneRadialMenu"
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path
                v-for="(segment, segmentIndex) in markerRadialIconPaths('close')"
                :key="`zone-center-${segmentIndex}`"
                :d="segment"
              />
            </svg>
            <span>Close</span>
          </button>
        </div>

        <div ref="markerToolbarRef" class="webmap-toolbar">
          <div class="webmap-toolbar-row">
            <button
              type="button"
              class="webmap-marker-trigger"
              :aria-expanded="markerToolbarOpen"
              aria-haspopup="menu"
              @click="toggleMarkerToolbar"
              @mouseenter="setToolbarHoverHint(markerHintText)"
              @mouseleave="clearToolbarHoverHint"
              @focus="setToolbarHoverHint(markerHintText)"
              @blur="clearToolbarHoverHint"
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
              :class="{ active: zoneMode || Boolean(zoneEditingId) }"
              @click="toggleZoneMode"
              @mouseenter="setToolbarHoverHint(zoneHintText)"
              @mouseleave="clearToolbarHoverHint"
              @focus="setToolbarHoverHint(zoneHintText)"
              @blur="clearToolbarHoverHint"
            >
              <span class="webmap-place-btn-icon" aria-hidden="true">[]</span>
              <span>
                {{
                  zoneEditingId
                    ? "Editing Zone"
                    : zoneMode
                      ? "Zone Draw Armed"
                      : "Draw Zone"
                }}
              </span>
            </button>
            <button
              v-if="zoneMode && zoneDraftPoints.length >= 3"
              type="button"
              class="webmap-place-btn"
              @click="completeZoneDraft"
              @mouseenter="setToolbarHoverHint('Finish polygon and enter a zone name')"
              @mouseleave="clearToolbarHoverHint"
            >
              <span>Finish Zone</span>
            </button>
            <button
              v-if="zoneEditingId"
              type="button"
              class="webmap-place-btn"
              @click="saveZoneEdit"
              @mouseenter="setToolbarHoverHint('Save zone geometry changes')"
              @mouseleave="clearToolbarHoverHint"
            >
              <span>Save Zone</span>
            </button>
            <button
              v-if="zoneEditingId"
              type="button"
              class="webmap-place-btn"
              @click="cancelZoneEdit"
              @mouseenter="setToolbarHoverHint('Discard zone geometry changes')"
              @mouseleave="clearToolbarHoverHint"
            >
              <span>Cancel Edit</span>
            </button>
          </div>

          <div v-if="toolbarHoverHint" class="webmap-toolbar-hover-hint" aria-live="polite">
            {{ toolbarHoverHint }}
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
          v-if="zonePromptOpen"
          ref="zonePromptRef"
          class="webmap-rename-popover"
          :style="zonePromptStyle"
          @click.stop
          @contextmenu.prevent
        >
          <div class="webmap-rename-title">{{ zonePromptMode === "create" ? "Name New Zone" : "Rename Zone" }}</div>
          <input
            v-model="zonePromptValue"
            class="webmap-rename-input"
            type="text"
            maxlength="96"
            placeholder="Zone name"
            @keydown.enter.prevent="submitZonePrompt"
            @keydown.esc.prevent="closeZonePrompt"
          />
          <div class="webmap-rename-actions">
            <button type="button" class="webmap-rename-btn" @click="closeZonePrompt">Cancel</button>
            <button type="button" class="webmap-rename-btn webmap-rename-btn--primary" @click="submitZonePrompt">
              {{ zonePromptBusy ? "Saving..." : "Save" }}
            </button>
          </div>
        </div>
        <div
          v-if="zoneAssignOpen"
          ref="zoneAssignPopoverRef"
          class="webmap-rename-popover webmap-zone-assign-popover"
          :style="zoneAssignStyle"
          @click.stop
          @contextmenu.prevent
        >
          <div class="webmap-rename-title">Assign Zone to Mission</div>
          <select v-model="zoneAssignMissionUid" class="webmap-rename-input" :disabled="zoneAssignBusy || zoneAssignMissionsLoading">
            <option value="" disabled>
              {{ zoneAssignMissionsLoading ? "Loading missions..." : "Select mission" }}
            </option>
            <option v-for="mission in zoneAssignMissions" :key="mission.uid" :value="mission.uid">
              {{ mission.name }}
            </option>
          </select>
          <div class="webmap-rename-actions">
            <button type="button" class="webmap-rename-btn" @click="closeZoneAssign">Cancel</button>
            <button
              type="button"
              class="webmap-rename-btn webmap-rename-btn--primary"
              :disabled="zoneAssignBusy || !zoneAssignMissionUid"
              @click="submitZoneAssign"
            >
              {{ zoneAssignBusy ? "Assigning..." : "Assign" }}
            </button>
          </div>
        </div>
        <div
          v-if="markerAssignOpen"
          ref="markerAssignPopoverRef"
          class="webmap-rename-popover webmap-zone-assign-popover"
          :style="markerAssignStyle"
          @click.stop
          @contextmenu.prevent
        >
          <div class="webmap-rename-title">Assign Marker to Mission</div>
          <select
            v-model="markerAssignMissionUid"
            class="webmap-rename-input"
            :disabled="markerAssignBusy || markerAssignMissionsLoading"
          >
            <option value="" disabled>
              {{ markerAssignMissionsLoading ? "Loading missions..." : "Select mission" }}
            </option>
            <option v-for="mission in markerAssignMissions" :key="mission.uid" :value="mission.uid">
              {{ mission.name }}
            </option>
          </select>
          <div class="webmap-rename-actions">
            <button type="button" class="webmap-rename-btn" @click="closeMarkerAssign">Cancel</button>
            <button
              type="button"
              class="webmap-rename-btn webmap-rename-btn--primary"
              :disabled="markerAssignBusy || !markerAssignMissionUid"
              @click="submitMarkerAssign"
            >
              {{ markerAssignBusy ? "Assigning..." : "Assign" }}
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
          <BaseButton
            variant="tab"
            size="sm"
            :class="{ 'cui-tab-active': activeMarkerTab === 'zones' }"
            @click="activeMarkerTab = 'zones'"
          >
            Zones
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
                {{ marker.category }} Â· {{ marker.lat.toFixed(4) }}, {{ marker.lon.toFixed(4) }}
              </div>
            </li>
          </ul>
        </div>

        <div v-else-if="activeMarkerTab === 'telemetry'" class="webmap-list-wrap cui-scrollbar">
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

        <div v-else class="webmap-list-wrap cui-scrollbar">
          <LoadingSkeleton v-if="zonesStore.loading" />
          <ul v-else class="webmap-list">
            <li
              v-for="zone in zonePagination.items"
              :key="zone.id"
              class="webmap-list-item"
              :class="{ 'webmap-list-item--selected': selectedZoneId === zone.id }"
              @click="focusZone(zone.id)"
            >
              <div class="webmap-zone-row">
                <div class="webmap-list-name">{{ zone.name }}</div>
                <div class="webmap-zone-actions">
                  <button type="button" class="webmap-zone-action" @click.stop="openZoneRename(zone.id)">Rename</button>
                  <button type="button" class="webmap-zone-action" @click.stop="startZoneEdit(zone.id)">Edit</button>
                  <button type="button" class="webmap-zone-action webmap-zone-action--danger" @click.stop="deleteZone(zone.id)">
                    Delete
                  </button>
                </div>
              </div>
              <div class="webmap-list-meta">{{ zone.points.length }} pts Â· {{ zoneAreaSummary(zone.points) }}</div>
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

        <div v-else-if="activeMarkerTab === 'telemetry'" class="webmap-pagination">
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

        <div v-else class="webmap-pagination">
          <span v-if="zonePagination.total">
            {{ zonePagination.startIndex }}-{{ zonePagination.endIndex }} / {{ zonePagination.total }}
          </span>
          <span v-else>No zones yet.</span>
          <div class="webmap-pagination-actions">
            <BaseButton
              variant="secondary"
              size="sm"
              icon-left="chevron-left"
              :disabled="zonePagination.page <= 1"
              @click="updateZonePage(-1)"
            >
              Prev
            </BaseButton>
            <BaseButton
              variant="secondary"
              size="sm"
              icon-left="chevron-right"
              :disabled="zonePagination.page >= zonePagination.totalPages"
              @click="updateZonePage(1)"
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
import { computed, nextTick, onMounted, onUnmounted, shallowRef, watch } from "vue";
import { ref } from "vue";
import { storeToRefs } from "pinia";
import maplibregl from "maplibre-gl";
import type { DataDrivenPropertyValueSpecification, ExpressionSpecification } from "@maplibre/maplibre-gl-style-spec";
import { get, put } from "../api/client";
import { endpoints } from "../api/endpoints";
import BaseButton from "../components/BaseButton.vue";
import BaseFormattedOutput from "../components/BaseFormattedOutput.vue";
import BaseInput from "../components/BaseInput.vue";
import LoadingSkeleton from "../components/LoadingSkeleton.vue";
import { WsClient } from "../api/ws";
import { useMapSettingsStore } from "../stores/map-settings";
import { useNavStore } from "../stores/nav";
import { useMarkersStore } from "../stores/markers";
import { useTelemetryStore } from "../stores/telemetry";
import { useToastStore } from "../stores/toasts";
import { useZonesStore } from "../stores/zones";
import { formatAreaLabel } from "../utils/geometry";
import type { GeoPoint } from "../utils/geometry";
import { closePolygonRing } from "../utils/geometry";
import { polygonAreaSquareMeters } from "../utils/geometry";
import { polygonCentroid } from "../utils/geometry";
import { polygonMidpoints } from "../utils/geometry";
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
import type { MissionRaw } from "../types/missions/raw";

type ScreenPoint = { x: number; y: number };
type MarkerRadialIcon = "edit" | "move" | "compass" | "assign" | "delete" | "inspect" | "back" | "close";
type MarkerRadialAction = "rename" | "move" | "compass" | "assign" | "delete" | "inspect";
type MarkerRadialMenuNode = {
  id: string;
  label: string;
  icon: MarkerRadialIcon;
  action?: MarkerRadialAction;
  children?: MarkerRadialMenuNode[];
};
type MarkerRadialMenuProfile = "regular" | "telemetry";
type ZoneRadialAction = "rename" | "move" | "delete" | "assign";
type ZoneRadialMenuNode = {
  id: string;
  label: string;
  icon: MarkerRadialIcon;
  action: ZoneRadialAction;
};
type ZoneMissionOption = {
  uid: string;
  name: string;
};

const markerRadialMenus: Record<MarkerRadialMenuProfile, MarkerRadialMenuNode[]> = {
  regular: [
    { id: "rename", label: "Edit", icon: "edit", action: "rename" },
    { id: "move", label: "Move", icon: "move", action: "move" },
    { id: "compass", label: "Compass", icon: "compass", action: "compass" },
    { id: "assign", label: "Assign", icon: "assign", action: "assign" },
    { id: "delete", label: "Delete", icon: "delete", action: "delete" },
  ],
  telemetry: [{ id: "inspect", label: "Inspect", icon: "inspect", action: "inspect" }],
};
const zoneRadialMenuItems: ZoneRadialMenuNode[] = [
  { id: "rename", label: "Edit", icon: "edit", action: "rename" },
  { id: "move", label: "Move", icon: "move", action: "move" },
  { id: "assign", label: "Assign", icon: "assign", action: "assign" },
  { id: "delete", label: "Delete", icon: "delete", action: "delete" },
];

const markerRadialIconMap: Record<MarkerRadialIcon, string[]> = {
  edit: [
    "M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25Z",
    "M14.06 4.94l3.75 3.75",
  ],
  move: [
    "M12 2v20",
    "M2 12h20",
    "M8 6l4-4 4 4",
    "M8 18l4 4 4-4",
    "M6 8l-4 4 4 4",
    "M18 8l4 4-4 4",
  ],
  compass: [
    "M12 3a9 9 0 1 0 0 18a9 9 0 0 0 0-18Z",
    "M15.6 8.4l-2.2 5-5 2.2 2.2-5 5-2.2Z",
  ],
  assign: [
    "M8.5 15.5a3 3 0 0 1 0-4.2l2.8-2.8a3 3 0 0 1 4.2 0",
    "M15.5 8.5a3 3 0 0 1 0 4.2l-2.8 2.8a3 3 0 0 1-4.2 0",
    "M9 15l6-6",
  ],
  delete: [
    "M4 7h16",
    "M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2",
    "M7 7l1 13h8l1-13",
    "M10 11v6",
    "M14 11v6",
  ],
  inspect: [
    "M1.5 12s4.5-7 10.5-7 10.5 7 10.5 7-4.5 7-10.5 7S1.5 12 1.5 12Z",
    "M12 9a3 3 0 1 0 0 6a3 3 0 0 0 0-6Z",
  ],
  back: ["M15 18l-6-6 6-6"],
  close: [
    "M6 6l12 12",
    "M18 6 6 18",
  ],
};

const telemetry = useTelemetryStore();
const markersStore = useMarkersStore();
const zonesStore = useZonesStore();
const toastStore = useToastStore();
const mapSettingsStore = useMapSettingsStore();
const navStore = useNavStore();
const { isCollapsed: isNavCollapsed } = storeToRefs(navStore);
const { mapView, showMarkerLabels } = storeToRefs(mapSettingsStore);
const mapContainer = ref<HTMLDivElement | null>(null);
const mapInstance = shallowRef<maplibregl.Map | null>(null);
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
let zoneInteractionReady = false;
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
const markerRadialMenuRef = ref<HTMLDivElement | null>(null);
const zoneRadialMenuRef = ref<HTMLDivElement | null>(null);
const hoveredOperatorMarkerId = ref<string | null>(null);
const hoveredOperatorMarkerPoint = ref<ScreenPoint | null>(null);
const markerRadialMenuMarkerId = ref<string | null>(null);
const markerRadialMenuPoint = ref<ScreenPoint | null>(null);
const markerRadialMenuPath = ref<string[]>([]);
const markerRadialMenuProfile = ref<MarkerRadialMenuProfile>("regular");
const markerMoveArmId = ref<string | null>(null);
const markerCompassMarkerId = ref<string | null>(null);
const markerCompassPoint = ref<ScreenPoint | null>(null);
const creatingMarker = ref(false);
const draggingMarkerId = ref<string | null>(null);
const draggingMarkerOrigin = ref<{ lat: number; lon: number } | null>(null);
const dragPositions = ref(new Map<string, { lat: number; lon: number }>());
const zoneMode = ref(false);
const zoneDraftPoints = ref<GeoPoint[]>([]);
const zoneEditingId = ref("");
const zoneEditingPoints = ref<GeoPoint[]>([]);
const selectedZoneId = ref("");
const zoneDraggingVertexIndex = ref<number | null>(null);
const zonePromptOpen = ref(false);
const zonePromptMode = ref<"create" | "rename">("create");
const zonePromptZoneId = ref("");
const zonePromptValue = ref("");
const zonePromptPosition = ref({ left: 12, top: 12 });
const zonePromptBusy = ref(false);
const zonePromptRef = ref<HTMLDivElement | null>(null);
const zoneRadialMenuZoneId = ref<string | null>(null);
const zoneRadialMenuPoint = ref<ScreenPoint | null>(null);
const zoneAssignOpen = ref(false);
const zoneAssignZoneId = ref("");
const zoneAssignMissionUid = ref("");
const zoneAssignPosition = ref({ left: 12, top: 12 });
const zoneAssignBusy = ref(false);
const zoneAssignMissions = ref<ZoneMissionOption[]>([]);
const zoneAssignMissionsLoading = ref(false);
const zoneAssignPopoverRef = ref<HTMLDivElement | null>(null);
const markerAssignOpen = ref(false);
const markerAssignMarkerId = ref("");
const markerAssignMissionUid = ref("");
const markerAssignPosition = ref({ left: 12, top: 12 });
const markerAssignBusy = ref(false);
const markerAssignMissions = ref<ZoneMissionOption[]>([]);
const markerAssignMissionsLoading = ref(false);
const markerAssignPopoverRef = ref<HTMLDivElement | null>(null);
const toolbarHoverHint = ref("");
type MarkerTab = "operator" | "telemetry" | "zones";
const activeMarkerTab = ref<MarkerTab>("operator");
const ITEMS_PER_PAGE = 10;
const operatorPage = ref(1);
const telemetryPage = ref(1);
const zonePage = ref(1);

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
const toZoneMissionOptions = (missions: MissionRaw[]): ZoneMissionOption[] => {
  return missions
    .map((entry) => {
      const uid = String(entry.uid ?? "").trim();
      if (!uid) {
        return null;
      }
      const name = String(entry.mission_name ?? "").trim() || uid;
      return { uid, name };
    })
    .filter((entry): entry is ZoneMissionOption => entry !== null)
    .sort((left, right) => left.name.localeCompare(right.name));
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
const zoneHintText = computed(() => {
  if (zoneEditingId.value) {
    return "Edit vertices, then save or cancel";
  }
  if (zoneMode.value) {
    return zoneDraftPoints.value.length >= 3
      ? "Click map to add points, double-click to finish"
      : "Click map to add at least three points";
  }
  return "Arm zone drawing to create a polygon";
});
const setToolbarHoverHint = (hint: string) => {
  toolbarHoverHint.value = hint;
};
const clearToolbarHoverHint = () => {
  toolbarHoverHint.value = "";
};
const markerRenameStyle = computed(() => ({
  left: `${markerRenamePosition.value.left}px`,
  top: `${markerRenamePosition.value.top}px`
}));
const zonePromptStyle = computed(() => ({
  left: `${zonePromptPosition.value.left}px`,
  top: `${zonePromptPosition.value.top}px`
}));
const zoneAssignStyle = computed(() => ({
  left: `${zoneAssignPosition.value.left}px`,
  top: `${zoneAssignPosition.value.top}px`
}));
const markerAssignStyle = computed(() => ({
  left: `${markerAssignPosition.value.left}px`,
  top: `${markerAssignPosition.value.top}px`
}));
const MARKER_RADIAL_MENU_EDGE_PADDING = 162;
const MARKER_COMPASS_EDGE_PADDING = 176;
const markerRadialIconPaths = (icon: MarkerRadialIcon) => markerRadialIconMap[icon] ?? [];
const toScreenPoint = (point: { x: number; y: number }): ScreenPoint => ({
  x: Number(point.x),
  y: Number(point.y),
});
const clampPointToContainer = (point: ScreenPoint, padding = 0): ScreenPoint => {
  const container = mapContainer.value;
  if (!container) {
    return point;
  }
  return {
    x: Math.min(Math.max(point.x, padding), Math.max(padding, container.clientWidth - padding)),
    y: Math.min(Math.max(point.y, padding), Math.max(padding, container.clientHeight - padding)),
  };
};
const resolveMarkerScreenPoint = (markerId: string, fallback?: ScreenPoint): ScreenPoint | null => {
  const map = mapInstance.value;
  if (!map) {
    return fallback ?? null;
  }
  const marker = markersStore.markerIndex.get(markerId);
  if (marker) {
    const override = dragPositions.value.get(markerId);
    const lat = override?.lat ?? marker.lat;
    const lon = override?.lon ?? marker.lon;
    const projected = map.project([lon, lat]);
    return { x: projected.x, y: projected.y };
  }
  const telemetryMarker = markerIndex.value.get(markerId);
  if (telemetryMarker) {
    const projected = map.project([telemetryMarker.lon, telemetryMarker.lat]);
    return { x: projected.x, y: projected.y };
  }
  return fallback ?? null;
};
const resolveMarkerType = (markerId: string): MarkerRadialMenuProfile | null => {
  if (markersStore.markerIndex.has(markerId)) {
    return "regular";
  }
  if (markerIndex.value.has(markerId)) {
    return "telemetry";
  }
  return null;
};
const resolveMarkerLabel = (markerId: string): string => {
  const operatorMarker = markersStore.markerIndex.get(markerId);
  if (operatorMarker) {
    return operatorMarker.name;
  }
  const telemetryMarker = markerIndex.value.get(markerId);
  if (telemetryMarker) {
    return telemetryMarker.name;
  }
  return "Marker";
};
const clearHoveredOperatorMarker = () => {
  hoveredOperatorMarkerId.value = null;
  hoveredOperatorMarkerPoint.value = null;
};
const closeMarkerCompass = () => {
  markerCompassMarkerId.value = null;
  markerCompassPoint.value = null;
};
const closeMarkerRadialMenu = () => {
  markerRadialMenuMarkerId.value = null;
  markerRadialMenuPoint.value = null;
  markerRadialMenuPath.value = [];
};
const closeZoneRadialMenu = () => {
  zoneRadialMenuZoneId.value = null;
  zoneRadialMenuPoint.value = null;
};
const closeZoneAssign = () => {
  zoneAssignOpen.value = false;
  zoneAssignZoneId.value = "";
  zoneAssignMissionUid.value = "";
  zoneAssignBusy.value = false;
};
const closeMarkerAssign = () => {
  markerAssignOpen.value = false;
  markerAssignMarkerId.value = "";
  markerAssignMissionUid.value = "";
  markerAssignBusy.value = false;
};
const dismissRadialMenus = () => {
  markerToolbarOpen.value = false;
  closeMarkerRadialMenu();
  closeZoneRadialMenu();
  closeZoneAssign();
  closeMarkerAssign();
  markerMoveArmId.value = null;
  closeMarkerCompass();
  clearHoveredOperatorMarker();
  if (markerRenameOpen.value) {
    closeMarkerRename();
  }
  if (zonePromptOpen.value) {
    closeZonePrompt();
  }
};
const openHoverMarkerRadialMenu = (markerId: string, point: ScreenPoint) => {
  const anchored = resolveMarkerScreenPoint(markerId, point);
  if (!anchored) {
    return;
  }
  if (markerRadialMenuMarkerId.value === markerId) {
    markerRadialMenuPoint.value = anchored;
    hoveredOperatorMarkerId.value = markerId;
    hoveredOperatorMarkerPoint.value = anchored;
    return;
  }
  openMarkerRadialMenu(markerId, anchored);
};
const openHoverZoneRadialMenu = (zoneId: string, point: ScreenPoint) => {
  if (zoneRadialMenuZoneId.value === zoneId) {
    zoneRadialMenuPoint.value = point;
    return;
  }
  openZoneRadialMenu(zoneId, point);
};
const resolveMarkerRadialMenuProfile = (markerId: string): MarkerRadialMenuProfile =>
  resolveMarkerType(markerId) ?? "regular";
const resolveMarkerRadialMenuLevel = (
  profile: MarkerRadialMenuProfile,
  path: string[]
): MarkerRadialMenuNode[] => {
  let level = markerRadialMenus[profile];
  for (const segment of path) {
    const node = level.find((item) => item.id === segment);
    if (!node?.children?.length) {
      return [];
    }
    level = node.children;
  }
  return level;
};
const markerRadialMenuItems = computed(() =>
  resolveMarkerRadialMenuLevel(markerRadialMenuProfile.value, markerRadialMenuPath.value)
);
const markerRadialMenuCenterIcon = computed<MarkerRadialIcon>(() =>
  markerRadialMenuPath.value.length ? "back" : "close"
);
const markerRadialMenuCenterLabel = computed(() =>
  markerRadialMenuPath.value.length ? "Back" : "Close"
);
watch(markerRadialMenuItems, (items) => {
  if (markerRadialMenuPath.value.length && markerRadialMenuMarkerId.value && !items.length) {
    markerRadialMenuPath.value = [];
  }
});
const markerRadialMenuStyle = computed(() => {
  if (!markerRadialMenuMarkerId.value || !markerRadialMenuPoint.value) {
    return null;
  }
  const clamped = clampPointToContainer(markerRadialMenuPoint.value, MARKER_RADIAL_MENU_EDGE_PADDING);
  return {
    left: `${clamped.x}px`,
    top: `${clamped.y}px`
  };
});
const zoneRadialMenuStyle = computed(() => {
  if (!zoneRadialMenuZoneId.value || !zoneRadialMenuPoint.value) {
    return null;
  }
  const clamped = clampPointToContainer(zoneRadialMenuPoint.value, MARKER_RADIAL_MENU_EDGE_PADDING);
  return {
    left: `${clamped.x}px`,
    top: `${clamped.y}px`
  };
});
const markerReticleMarkerId = computed(() =>
  markerRadialMenuMarkerId.value ?? hoveredOperatorMarkerId.value ?? markerCompassMarkerId.value
);
const markerReticlePoint = computed(() =>
  markerRadialMenuPoint.value ?? hoveredOperatorMarkerPoint.value ?? markerCompassPoint.value
);
const markerReticleLabel = computed(() => {
  const markerId = markerReticleMarkerId.value;
  if (!markerId) {
    return "";
  }
  return resolveMarkerLabel(markerId);
});
const markerReticleSubLabel = computed(() => {
  const markerId = markerReticleMarkerId.value;
  if (!markerId) {
    return "";
  }
  if (markerMoveArmId.value && markerMoveArmId.value === markerId) {
    return "Move Armed";
  }
  if (markerRadialMenuMarkerId.value && markerRadialMenuMarkerId.value === markerId) {
    return "Command Menu";
  }
  if (markerCompassMarkerId.value && markerCompassMarkerId.value === markerId) {
    return "Compass Active";
  }
  if (markersStore.markerIndex.has(markerId)) {
    return "Operator Marker";
  }
  if (markerIndex.value.has(markerId)) {
    return "User";
  }
  return "Marker";
});
const markerReticleStyle = computed(() => {
  const point = markerReticlePoint.value;
  if (!point || !markerReticleMarkerId.value) {
    return null;
  }
  return {
    left: `${point.x}px`,
    top: `${point.y}px`
  };
});
const markerCompassStyle = computed(() => {
  if (!markerCompassMarkerId.value || !markerCompassPoint.value) {
    return null;
  }
  const point = clampPointToContainer(markerCompassPoint.value, MARKER_COMPASS_EDGE_PADDING);
  return {
    left: `${point.x}px`,
    top: `${point.y}px`
  };
});
const markerCompassTicks = computed(() =>
  Array.from({ length: 72 }, (_, index) => {
    const degrees = index * 5;
    const radians = ((degrees - 90) * Math.PI) / 180;
    const major = degrees % 10 === 0;
    const innerRadius = major ? 133 : 139;
    const outerRadius = 146;
    return {
      id: degrees,
      major,
      x1: 160 + Math.cos(radians) * innerRadius,
      y1: 160 + Math.sin(radians) * innerRadius,
      x2: 160 + Math.cos(radians) * outerRadius,
      y2: 160 + Math.sin(radians) * outerRadius,
    };
  })
);
const markerCompassLabels = computed(() =>
  Array.from({ length: 12 }, (_, index) => {
    const degrees = index * 30;
    const radians = ((degrees - 90) * Math.PI) / 180;
    const labelValue = degrees === 0 ? "360" : String(degrees);
    const radius = 116;
    return {
      id: labelValue,
      text: labelValue,
      x: 160 + Math.cos(radians) * radius,
      y: 160 + Math.sin(radians) * radius + 4,
    };
  })
);
const markerRadialMenuItemStyle = (index: number, total: number) => {
  const count = Math.max(total, 1);
  const radius = count <= 3 ? 104 : count <= 6 ? 116 : 126;
  const angleDegrees = -90 + (360 / count) * index;
  const radians = (angleDegrees * Math.PI) / 180;
  const x = Math.cos(radians) * radius;
  const y = Math.sin(radians) * radius;
  return {
    transform: `translate(calc(-50% + ${x.toFixed(3)}px), calc(-50% + ${y.toFixed(3)}px))`
  };
};
const syncMarkerInteractionAnchors = () => {
  if (markerMoveArmId.value && !markersStore.markerIndex.has(markerMoveArmId.value)) {
    markerMoveArmId.value = null;
  }
  if (markerRadialMenuMarkerId.value) {
    const anchored = resolveMarkerScreenPoint(markerRadialMenuMarkerId.value);
    if (!anchored) {
      closeMarkerRadialMenu();
    } else {
      markerRadialMenuPoint.value = anchored;
    }
  }
  if (markerCompassMarkerId.value) {
    const anchored = resolveMarkerScreenPoint(markerCompassMarkerId.value);
    if (!anchored) {
      closeMarkerCompass();
    } else {
      markerCompassPoint.value = anchored;
    }
  }
};
const openMarkerRadialMenu = (markerId: string, point?: ScreenPoint) => {
  const anchored = resolveMarkerScreenPoint(markerId, point);
  if (!anchored) {
    return;
  }
  closeZoneRadialMenu();
  closeZoneAssign();
  closeMarkerAssign();
  closeMarkerCompass();
  markerRadialMenuProfile.value = resolveMarkerRadialMenuProfile(markerId);
  markerRadialMenuPath.value = [];
  markerRadialMenuMarkerId.value = markerId;
  markerRadialMenuPoint.value = anchored;
  hoveredOperatorMarkerId.value = markerId;
  hoveredOperatorMarkerPoint.value = anchored;
  markerMoveArmId.value = null;
};
const openZoneRadialMenu = (zoneId: string, point: ScreenPoint) => {
  closeMarkerRadialMenu();
  closeMarkerCompass();
  markerMoveArmId.value = null;
  closeZoneAssign();
  closeMarkerAssign();
  closeZonePrompt();
  if (markerRenameOpen.value) {
    closeMarkerRename();
  }
  markerToolbarOpen.value = false;
  clearHoveredOperatorMarker();
  selectedZoneId.value = zoneId;
  activeMarkerTab.value = "zones";
  zoneRadialMenuZoneId.value = zoneId;
  zoneRadialMenuPoint.value = point;
  renderZones();
};
const handleMarkerRadialMenuCenter = () => {
  if (!markerRadialMenuMarkerId.value) {
    return;
  }
  if (markerRadialMenuPath.value.length) {
    markerRadialMenuPath.value = markerRadialMenuPath.value.slice(0, -1);
    return;
  }
  closeMarkerRadialMenu();
};
const handleMarkerRadialMenuItem = (item: MarkerRadialMenuNode) => {
  const markerId = markerRadialMenuMarkerId.value;
  if (!markerId) {
    return;
  }
  if (item.children?.length) {
    markerRadialMenuPath.value = [...markerRadialMenuPath.value, item.id];
    return;
  }
  if (item.action === "inspect") {
    const telemetryMarker = markerIndex.value.get(markerId);
    closeMarkerRadialMenu();
    if (telemetryMarker) {
      openInspector(telemetryMarker, true);
    }
    return;
  }
  if (item.action === "rename") {
    const anchor = markerRadialMenuPoint.value ?? resolveMarkerScreenPoint(markerId);
    closeMarkerRadialMenu();
    if (anchor) {
      openMarkerRename(markerId, anchor);
    }
    return;
  }
  if (item.action === "move") {
    markerMoveArmId.value = markerId;
    closeMarkerRadialMenu();
    toastStore.push("Press and hold this marker to move it.", "info");
    return;
  }
  if (item.action === "assign") {
    const anchor = markerRadialMenuPoint.value ?? resolveMarkerScreenPoint(markerId);
    closeMarkerRadialMenu();
    if (anchor) {
      void openMarkerAssignPopover(markerId, anchor);
    }
    return;
  }
  if (item.action === "delete") {
    closeMarkerRadialMenu();
    markerMoveArmId.value = null;
    closeMarkerCompass();
    clearHoveredOperatorMarker();
    void markersStore
      .deleteMarker(markerId)
      .then(() => {
        renderOperatorMarkers();
        toastStore.push("Marker deleted.", "warning");
      })
      .catch(() => {
        toastStore.push("Unable to delete marker.", "danger");
      });
    return;
  }
  if (item.action === "compass") {
    const shouldCloseCompass = markerCompassMarkerId.value === markerId;
    const anchor = markerRadialMenuPoint.value ?? resolveMarkerScreenPoint(markerId);
    closeMarkerRadialMenu();
    if (shouldCloseCompass) {
      closeMarkerCompass();
      return;
    }
    if (anchor) {
      markerCompassMarkerId.value = markerId;
      markerCompassPoint.value = anchor;
    }
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
const zonesSorted = computed(() => {
  return [...zonesStore.zones].sort((left, right) => {
    const leftTime = toTimestamp(left.updatedAt ?? left.createdAt);
    const rightTime = toTimestamp(right.updatedAt ?? right.createdAt);
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
const zonePagination = computed(() => buildPagination(zonesSorted.value, zonePage.value));

const updateOperatorPage = (delta: number) => {
  const totalPages = operatorPagination.value.totalPages;
  operatorPage.value = Math.min(totalPages, Math.max(1, operatorPage.value + delta));
};

const updateTelemetryPage = (delta: number) => {
  const totalPages = telemetryPagination.value.totalPages;
  telemetryPage.value = Math.min(totalPages, Math.max(1, telemetryPage.value + delta));
};

const updateZonePage = (delta: number) => {
  const totalPages = zonePagination.value.totalPages;
  zonePage.value = Math.min(totalPages, Math.max(1, zonePage.value + delta));
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

watch(
  () => zonesSorted.value.length,
  (total) => {
    const totalPages = Math.max(1, Math.ceil(total / ITEMS_PER_PAGE));
    if (zonePage.value > totalPages) {
      zonePage.value = totalPages;
    }
  }
);

const selectedZone = computed(() => {
  if (!selectedZoneId.value) {
    return undefined;
  }
  return zonesStore.zoneIndex.get(selectedZoneId.value);
});

watch(zoneMode, (armed) => {
  const map = mapInstance.value;
  if (!map) {
    return;
  }
  if (armed) {
    map.doubleClickZoom.disable();
    return;
  }
  if (!zoneEditingId.value) {
    map.doubleClickZoom.enable();
  }
});

watch(
  () => zonesStore.zones,
  () => {
    renderZones();
  },
  { deep: true }
);

watch(selectedZoneId, () => {
  renderZones();
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
  telemetryPage.value = 1;
  await telemetry.fetchTelemetry(sinceSeconds());
  renderMarkers();
  subscribeTelemetry();
};

const toggleZoneMode = () => {
  markerToolbarOpen.value = false;
  closeMarkerRadialMenu();
  closeZoneRadialMenu();
  closeZoneAssign();
  closeMarkerAssign();
  closeMarkerCompass();
  markerMoveArmId.value = null;
  clearHoveredOperatorMarker();
  markerMode.value = false;
  if (zoneEditingId.value) {
    cancelZoneEdit();
    return;
  }
  zoneMode.value = !zoneMode.value;
  if (!zoneMode.value) {
    zoneDraftPoints.value = [];
  }
  renderZones();
};

const toggleMarkerToolbar = () => {
  closeMarkerRadialMenu();
  closeZoneRadialMenu();
  closeZoneAssign();
  closeMarkerAssign();
  markerToolbarOpen.value = !markerToolbarOpen.value;
};

const selectMarkerSymbol = (symbolId: string) => {
  closeMarkerRadialMenu();
  closeZoneRadialMenu();
  closeZoneAssign();
  closeMarkerAssign();
  closeMarkerCompass();
  markerMoveArmId.value = null;
  markerCategory.value = symbolId;
  if (zoneMode.value) {
    zoneMode.value = false;
    zoneDraftPoints.value = [];
  }
  markerMode.value = true;
  markerToolbarOpen.value = false;
};

const zoneAreaSummary = (points: GeoPoint[]) => {
  const area = polygonAreaSquareMeters(points);
  const km2 = area / 1_000_000;
  return `${km2.toFixed(2)} kmÂ²`;
};

const closeZonePrompt = () => {
  zonePromptOpen.value = false;
  zonePromptMode.value = "create";
  zonePromptZoneId.value = "";
  zonePromptValue.value = "";
  zonePromptBusy.value = false;
};

const openZonePrompt = (
  mode: "create" | "rename",
  options: { zoneId?: string; value?: string; point?: { x: number; y: number } } = {}
) => {
  closeZoneAssign();
  closeMarkerAssign();
  const { zoneId = "", value = "", point = { x: 12, y: 12 } } = options;
  const container = mapContainer.value;
  if (!container) {
    return;
  }
  const width = 260;
  const height = 140;
  const left = Math.min(Math.max(point.x + 12, 12), Math.max(12, container.clientWidth - width - 12));
  const top = Math.min(Math.max(point.y + 12, 12), Math.max(12, container.clientHeight - height - 12));
  zonePromptMode.value = mode;
  zonePromptZoneId.value = zoneId;
  zonePromptValue.value = value;
  zonePromptPosition.value = { left, top };
  zonePromptOpen.value = true;
};

const loadZoneAssignMissions = async (): Promise<void> => {
  zoneAssignMissionsLoading.value = true;
  try {
    const missions = await get<MissionRaw[]>(endpoints.r3aktMissions);
    zoneAssignMissions.value = toZoneMissionOptions(missions);
  } catch (error) {
    zoneAssignMissions.value = [];
    toastStore.push("Unable to load missions.", "danger");
  } finally {
    zoneAssignMissionsLoading.value = false;
  }
};

const loadMarkerAssignMissions = async (): Promise<void> => {
  markerAssignMissionsLoading.value = true;
  try {
    const missions = await get<MissionRaw[]>(endpoints.r3aktMissions);
    markerAssignMissions.value = toZoneMissionOptions(missions);
  } catch (error) {
    markerAssignMissions.value = [];
    toastStore.push("Unable to load missions.", "danger");
  } finally {
    markerAssignMissionsLoading.value = false;
  }
};

const openMarkerAssignPopover = async (markerId: string, point: ScreenPoint) => {
  const container = mapContainer.value;
  if (!container) {
    return;
  }
  closeZoneAssign();
  closeMarkerAssign();
  closeZoneRadialMenu();
  closeZonePrompt();
  if (markerRenameOpen.value) {
    closeMarkerRename();
  }
  const width = 280;
  const height = 148;
  const left = Math.min(Math.max(point.x + 12, 12), Math.max(12, container.clientWidth - width - 12));
  const top = Math.min(Math.max(point.y + 12, 12), Math.max(12, container.clientHeight - height - 12));
  markerAssignMarkerId.value = markerId;
  markerAssignMissionUid.value = "";
  markerAssignPosition.value = { left, top };
  markerAssignOpen.value = true;
  await loadMarkerAssignMissions();
  if (!markerAssignMissions.value.length) {
    toastStore.push("No missions available for assignment.", "warning");
    closeMarkerAssign();
    return;
  }
  markerAssignMissionUid.value = markerAssignMissions.value[0].uid;
};

const submitMarkerAssign = async () => {
  const markerId = markerAssignMarkerId.value.trim();
  const missionUid = markerAssignMissionUid.value.trim();
  if (!markerId || !missionUid || markerAssignBusy.value) {
    return;
  }
  markerAssignBusy.value = true;
  try {
    await put(`${endpoints.r3aktMissions}/${encodeURIComponent(missionUid)}/markers/${encodeURIComponent(markerId)}`);
    toastStore.push("Marker assigned to mission.", "success");
    closeMarkerAssign();
  } catch (error) {
    toastStore.push("Unable to assign marker to mission.", "danger");
  } finally {
    markerAssignBusy.value = false;
  }
};

const openZoneAssignPopover = async (zoneId: string, point: ScreenPoint) => {
  const container = mapContainer.value;
  if (!container) {
    return;
  }
  closeZoneRadialMenu();
  closeMarkerAssign();
  closeZonePrompt();
  if (markerRenameOpen.value) {
    closeMarkerRename();
  }
  const width = 280;
  const height = 148;
  const left = Math.min(Math.max(point.x + 12, 12), Math.max(12, container.clientWidth - width - 12));
  const top = Math.min(Math.max(point.y + 12, 12), Math.max(12, container.clientHeight - height - 12));
  zoneAssignZoneId.value = zoneId;
  zoneAssignMissionUid.value = "";
  zoneAssignPosition.value = { left, top };
  zoneAssignOpen.value = true;
  await loadZoneAssignMissions();
  if (!zoneAssignMissions.value.length) {
    toastStore.push("No missions available for assignment.", "warning");
    closeZoneAssign();
    return;
  }
  zoneAssignMissionUid.value = zoneAssignMissions.value[0].uid;
};

const submitZoneAssign = async () => {
  const zoneId = zoneAssignZoneId.value.trim();
  const missionUid = zoneAssignMissionUid.value.trim();
  if (!zoneId || !missionUid || zoneAssignBusy.value) {
    return;
  }
  zoneAssignBusy.value = true;
  try {
    await put(`${endpoints.r3aktMissions}/${encodeURIComponent(missionUid)}/zones/${encodeURIComponent(zoneId)}`);
    toastStore.push("Zone assigned to mission.", "success");
    closeZoneAssign();
  } catch (error) {
    toastStore.push("Unable to assign zone to mission.", "danger");
  } finally {
    zoneAssignBusy.value = false;
  }
};

const handleZoneRadialMenuItem = (item: ZoneRadialMenuNode) => {
  const zoneId = zoneRadialMenuZoneId.value;
  if (!zoneId) {
    return;
  }
  if (item.action === "rename") {
    closeZoneRadialMenu();
    openZoneRename(zoneId);
    return;
  }
  if (item.action === "move") {
    closeZoneRadialMenu();
    startZoneEdit(zoneId);
    toastStore.push("Zone edit mode active. Drag vertices to reposition geometry.", "info");
    return;
  }
  if (item.action === "delete") {
    closeZoneRadialMenu();
    void deleteZone(zoneId);
    return;
  }
  if (item.action === "assign") {
    let anchor = zoneRadialMenuPoint.value;
    if (!anchor && mapInstance.value) {
      const zone = zonesStore.zoneIndex.get(zoneId);
      const centroid = zone ? (polygonCentroid(zone.points) ?? zone.points[0]) : null;
      if (centroid) {
        const projected = mapInstance.value.project([centroid.lon, centroid.lat]);
        anchor = { x: projected.x, y: projected.y };
      }
    }
    if (!anchor) {
      return;
    }
    void openZoneAssignPopover(zoneId, anchor);
  }
};

const completeZoneDraft = () => {
  if (!mapInstance.value || zoneDraftPoints.value.length < 3) {
    toastStore.push("Add at least 3 points to create a zone.", "warning");
    return;
  }
  const lastPoint = zoneDraftPoints.value[zoneDraftPoints.value.length - 1];
  const projected = mapInstance.value.project([lastPoint.lon, lastPoint.lat]);
  openZonePrompt("create", { point: { x: projected.x, y: projected.y } });
};

const submitZonePrompt = async () => {
  const name = zonePromptValue.value.trim();
  if (!name || zonePromptBusy.value) {
    return;
  }
  zonePromptBusy.value = true;
  try {
    if (zonePromptMode.value === "create") {
      if (zoneDraftPoints.value.length < 3) {
        toastStore.push("A zone requires at least 3 points.", "warning");
        return;
      }
      const created = await zonesStore.createZone({
        name,
        points: zoneDraftPoints.value.map((point) => ({ lat: point.lat, lon: point.lon })),
      });
      selectedZoneId.value = created.id;
      activeMarkerTab.value = "zones";
      zoneMode.value = false;
      zoneDraftPoints.value = [];
      toastStore.push("Zone created.", "success");
    } else {
      const zoneId = zonePromptZoneId.value;
      if (!zoneId) {
        return;
      }
      await zonesStore.updateZone(zoneId, { name });
      toastStore.push("Zone renamed.", "success");
    }
    closeZonePrompt();
    renderZones();
  } catch (error) {
    toastStore.push("Unable to save zone.", "danger");
  } finally {
    zonePromptBusy.value = false;
  }
};

const startZoneEdit = (zoneId: string) => {
  const zone = zonesStore.zoneIndex.get(zoneId);
  if (!zone) {
    return;
  }
  closeZoneRadialMenu();
  closeZoneAssign();
  closeMarkerAssign();
  closeMarkerRadialMenu();
  closeMarkerCompass();
  markerMoveArmId.value = null;
  clearHoveredOperatorMarker();
  zoneMode.value = false;
  markerMode.value = false;
  zoneDraftPoints.value = [];
  selectedZoneId.value = zoneId;
  zoneEditingId.value = zoneId;
  zoneEditingPoints.value = zone.points.map((point) => ({ lat: point.lat, lon: point.lon }));
  activeMarkerTab.value = "zones";
  renderZones();
};

const cancelZoneEdit = () => {
  zoneEditingId.value = "";
  zoneEditingPoints.value = [];
  zoneDraggingVertexIndex.value = null;
  renderZones();
};

const saveZoneEdit = async () => {
  if (!zoneEditingId.value || zoneEditingPoints.value.length < 3) {
    return;
  }
  try {
    await zonesStore.updateZone(zoneEditingId.value, {
      points: zoneEditingPoints.value.map((point) => ({ lat: point.lat, lon: point.lon })),
    });
    toastStore.push("Zone updated.", "success");
    cancelZoneEdit();
  } catch (error) {
    toastStore.push("Unable to update zone.", "danger");
  }
};

const focusZone = (zoneId: string) => {
  const zone = zonesStore.zoneIndex.get(zoneId);
  if (!zone || !zone.points.length || !mapInstance.value) {
    return;
  }
  selectedZoneId.value = zoneId;
  activeMarkerTab.value = "zones";
  const bounds = zone.points.reduce(
    (acc, point) => {
      acc.minLat = Math.min(acc.minLat, point.lat);
      acc.maxLat = Math.max(acc.maxLat, point.lat);
      acc.minLon = Math.min(acc.minLon, point.lon);
      acc.maxLon = Math.max(acc.maxLon, point.lon);
      return acc;
    },
    { minLat: Number.POSITIVE_INFINITY, maxLat: Number.NEGATIVE_INFINITY, minLon: Number.POSITIVE_INFINITY, maxLon: Number.NEGATIVE_INFINITY }
  );
  mapInstance.value.fitBounds(
    [
      [bounds.minLon, bounds.minLat],
      [bounds.maxLon, bounds.maxLat],
    ],
    { padding: 48, duration: 400 }
  );
  renderZones();
};

const openZoneRename = (zoneId: string) => {
  const zone = zonesStore.zoneIndex.get(zoneId);
  if (!zone || !mapInstance.value) {
    return;
  }
  const centroid = polygonCentroid(zone.points) ?? zone.points[0];
  const projected = mapInstance.value.project([centroid.lon, centroid.lat]);
  openZonePrompt("rename", {
    zoneId,
    value: zone.name,
    point: { x: projected.x, y: projected.y },
  });
};

const deleteZone = async (zoneId: string) => {
  try {
    if (zoneRadialMenuZoneId.value === zoneId) {
      closeZoneRadialMenu();
    }
    if (zoneAssignZoneId.value === zoneId) {
      closeZoneAssign();
    }
    await zonesStore.deleteZone(zoneId);
    if (selectedZoneId.value === zoneId) {
      selectedZoneId.value = "";
    }
    if (zoneEditingId.value === zoneId) {
      cancelZoneEdit();
    }
    toastStore.push("Zone deleted.", "warning");
    renderZones();
  } catch (error) {
    toastStore.push("Unable to delete zone.", "danger");
  }
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
  closeMarkerRadialMenu();
  closeMarkerCompass();
  closeMarkerAssign();
  markerMoveArmId.value = null;
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
  clearHoveredOperatorMarker();
  if (!draggingMarkerId.value && mapInstance.value) {
    mapInstance.value.getCanvas().style.cursor = "";
  }
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
  return map.queryRenderedFeatures([point.x, point.y], { layers: existingLayers }).length > 0;
};

const handleDocumentPointerDown = (event: MouseEvent) => {
  const target = event.target as Node | null;
  if (zonePromptOpen.value && zonePromptRef.value) {
    if (!target || !zonePromptRef.value.contains(target)) {
      closeZonePrompt();
    }
  }
  if (zoneAssignOpen.value && zoneAssignPopoverRef.value) {
    if (!target || !zoneAssignPopoverRef.value.contains(target)) {
      closeZoneAssign();
    }
  }
  if (markerAssignOpen.value && markerAssignPopoverRef.value) {
    if (!target || !markerAssignPopoverRef.value.contains(target)) {
      closeMarkerAssign();
    }
  }
  if (markerToolbarOpen.value && markerToolbarRef.value) {
    if (!target || !markerToolbarRef.value.contains(target)) {
      markerToolbarOpen.value = false;
    }
  }
  if (markerRadialMenuMarkerId.value && markerRadialMenuRef.value) {
    if (!target || !markerRadialMenuRef.value.contains(target)) {
      closeMarkerRadialMenu();
      markerMoveArmId.value = null;
    }
  }
  if (zoneRadialMenuZoneId.value && zoneRadialMenuRef.value) {
    if (!target || !zoneRadialMenuRef.value.contains(target)) {
      closeZoneRadialMenu();
    }
  }
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
  closeMarkerRadialMenu();
  closeZoneRadialMenu();
  closeZoneAssign();
  closeMarkerAssign();
  closeMarkerCompass();
  markerMoveArmId.value = null;
  clearHoveredOperatorMarker();
  mapInstance.value.flyTo({ center: [marker.lon, marker.lat], zoom: 9 });
};

const handleMapClick = (event: maplibregl.MapMouseEvent) => {
  dismissRadialMenus();
  if (zoneMode.value) {
    const clickDetail = (event.originalEvent as MouseEvent | undefined)?.detail ?? 1;
    if (clickDetail > 1) {
      return;
    }
    if (
      pointHitsRenderedLayer(event.point, [
        "operator-marker-layer",
        "operator-marker-clusters",
        "operator-marker-cluster-count",
        "telemetry-icons",
        "telemetry-clusters",
        "telemetry-cluster-count",
        "zone-fill",
        "zone-outline",
        "zone-handle-hit",
        "zone-handle-vertices",
        "zone-handle-midpoints",
      ])
    ) {
      return;
    }
    zoneDraftPoints.value = [...zoneDraftPoints.value, { lat: event.lngLat.lat, lon: event.lngLat.lng }];
    renderZones();
    return;
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

const handleMapContextMenu = (event: maplibregl.MapMouseEvent) => {
  event.preventDefault();
  (event.originalEvent as MouseEvent | undefined)?.preventDefault?.();
  dismissRadialMenus();
};

const handleMapDoubleClick = (event: maplibregl.MapMouseEvent) => {
  if (!zoneMode.value) {
    return;
  }
  event.preventDefault();
  (event.originalEvent as MouseEvent | undefined)?.preventDefault?.();
  completeZoneDraft();
};

const handleZoneVertexDrag = (event: maplibregl.MapMouseEvent) => {
  const index = zoneDraggingVertexIndex.value;
  if (index === null || !zoneEditingId.value) {
    return;
  }
  const next = [...zoneEditingPoints.value];
  next[index] = { lat: event.lngLat.lat, lon: event.lngLat.lng };
  zoneEditingPoints.value = next;
  renderZones();
};

const stopZoneVertexDrag = () => {
  const map = mapInstance.value;
  if (!map) {
    zoneDraggingVertexIndex.value = null;
    return;
  }
  map.off("mousemove", handleZoneVertexDrag);
  map.dragPan.enable();
  map.getCanvas().style.cursor = "";
  zoneDraggingVertexIndex.value = null;
};

const startZoneVertexDrag = (event: maplibregl.MapLayerMouseEvent) => {
  const map = mapInstance.value;
  if (!zoneEditingId.value || !map) {
    return;
  }
  const pointerEvent = event.originalEvent as MouseEvent | undefined;
  if (pointerEvent && pointerEvent.button !== 0) {
    return;
  }
  const feature =
    event.features?.[0] ??
    map.queryRenderedFeatures([event.point.x, event.point.y], {
      layers: ["zone-handle-hit", "zone-handle-vertices"],
    })[0];
  const rawIndex = feature?.properties?.index;
  const index = typeof rawIndex === "string" ? Number(rawIndex) : Number(rawIndex);
  if (!Number.isInteger(index) || index < 0 || index >= zoneEditingPoints.value.length) {
    return;
  }
  event.preventDefault();
  pointerEvent?.preventDefault?.();
  pointerEvent?.stopPropagation?.();
  zoneDraggingVertexIndex.value = index;
  map.dragPan.disable();
  map.getCanvas().style.cursor = "move";
  map.on("mousemove", handleZoneVertexDrag);
  map.once("mouseup", stopZoneVertexDrag);
  map.once("mouseleave", stopZoneVertexDrag);
};

const handleZoneMidpointClick = (event: maplibregl.MapLayerMouseEvent) => {
  if (!zoneEditingId.value) {
    return;
  }
  const feature = event.features?.[0];
  const rawIndex = feature?.properties?.edge_index;
  const edgeIndex = typeof rawIndex === "string" ? Number(rawIndex) : Number(rawIndex);
  if (!Number.isInteger(edgeIndex) || edgeIndex < 0) {
    return;
  }
  const next = [...zoneEditingPoints.value];
  const insertAt = Math.min(next.length, edgeIndex + 1);
  next.splice(insertAt, 0, { lat: event.lngLat.lat, lon: event.lngLat.lng });
  zoneEditingPoints.value = next;
  renderZones();
};

const handleZoneVertexContextMenu = (event: maplibregl.MapLayerMouseEvent) => {
  if (!zoneEditingId.value) {
    return;
  }
  const feature = event.features?.[0];
  const rawIndex = feature?.properties?.index;
  const index = typeof rawIndex === "string" ? Number(rawIndex) : Number(rawIndex);
  if (!Number.isInteger(index) || index < 0) {
    return;
  }
  event.preventDefault();
  (event.originalEvent as MouseEvent | undefined)?.preventDefault?.();
  if (zoneEditingPoints.value.length <= 3) {
    toastStore.push("A zone must keep at least 3 points.", "warning");
    return;
  }
  const next = [...zoneEditingPoints.value];
  next.splice(index, 1);
  zoneEditingPoints.value = next;
  renderZones();
};

const handleZoneContextMenu = (event: maplibregl.MapLayerMouseEvent) => {
  event.preventDefault();
  (event.originalEvent as MouseEvent | undefined)?.preventDefault?.();
  dismissRadialMenus();
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
const ZONE_FILL_COLOR = "#2d89ff";
const ZONE_SELECTED_FILL_COLOR = "#55a8ff";
const ZONE_OUTLINE_COLOR = "#78bfff";
const ZONE_HANDLE_COLOR = "#9fd8ff";
const ZONE_MIDPOINT_COLOR = "#6bb3ff";
const ZONE_LABEL_TEXT_COLOR = "#f3fbff";
const ZONE_LABEL_HALO_COLOR = "#06121E";

const resolveMarkerLabelField = (): DataDrivenPropertyValueSpecification<string> =>
  showMarkerLabels.value ? (["get", "name"] as ExpressionSpecification) : "";

const buildMarkerLabelLayout = (): {
  "text-field": DataDrivenPropertyValueSpecification<string>;
  "text-size": number;
  "text-offset": [number, number];
  "text-anchor": "top";
  "text-allow-overlap": true;
  "text-ignore-placement": true;
} => ({
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

const buildIconSizeExpression = (zoom: number): DataDrivenPropertyValueSpecification<number> => {
  const expression: ExpressionSpecification = [
    "*",
    ["coalesce", ["get", "iconScale"], TELEMETRY_ICON_SCALE],
    resolveZoomScale(zoom)
  ];
  return expression;
};

const buildTelemetryIconSizeExpression = (zoom: number): DataDrivenPropertyValueSpecification<number> => {
  const expression: ExpressionSpecification = ["*", TELEMETRY_ICON_SCALE, resolveZoomScale(zoom)];
  return expression;
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
  syncMarkerInteractionAnchors();
};

const handleClusterZoom = () => {
  if (!mapInstance.value || !mapReady.value) {
    return;
  }
  renderZones();
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

const toZoneCoordinates = (points: GeoPoint[]) => {
  return [closePolygonRing(points).map((point) => [point.lon, point.lat])] as [number, number][][];
};

const buildZoneFeatureCollection = () => {
  const features = zonesStore.zones
    .map((zone) => {
      const points = zone.id === zoneEditingId.value ? zoneEditingPoints.value : zone.points;
      if (points.length < 3) {
        return null;
      }
      return {
        type: "Feature",
        geometry: {
          type: "Polygon",
          coordinates: toZoneCoordinates(points),
        },
        properties: {
          id: zone.id,
          name: zone.name,
          selected: selectedZoneId.value === zone.id ? 1 : 0,
        },
      } as GeoJSON.Feature<GeoJSON.Polygon>;
    })
    .filter((feature): feature is GeoJSON.Feature<GeoJSON.Polygon> => feature !== null);

  return {
    type: "FeatureCollection",
    features,
  } as GeoJSON.FeatureCollection;
};

const buildDraftZoneFeatureCollection = () => {
  const points = zoneDraftPoints.value;
  if (!zoneMode.value || points.length < 2) {
    return { type: "FeatureCollection", features: [] } as GeoJSON.FeatureCollection;
  }
  if (points.length >= 3) {
    return {
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          geometry: {
            type: "Polygon",
            coordinates: toZoneCoordinates(points),
          },
          properties: {},
        },
      ],
    } as GeoJSON.FeatureCollection;
  }
  return {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        geometry: {
          type: "LineString",
          coordinates: points.map((point) => [point.lon, point.lat]),
        },
        properties: {},
      },
    ],
  } as GeoJSON.FeatureCollection;
};

const buildZoneHandleFeatureCollection = () => {
  const points = zoneEditingId.value
    ? zoneEditingPoints.value
    : zoneMode.value
      ? zoneDraftPoints.value
      : [];
  return {
    type: "FeatureCollection",
    features: points.map((point, index) => ({
      type: "Feature",
      geometry: {
        type: "Point",
        coordinates: [point.lon, point.lat],
      },
      properties: {
        index,
      },
    })),
  } as GeoJSON.FeatureCollection;
};

const buildZoneMidpointFeatureCollection = () => {
  if (!zoneEditingId.value || zoneEditingPoints.value.length < 2) {
    return { type: "FeatureCollection", features: [] } as GeoJSON.FeatureCollection;
  }
  const midpoints = polygonMidpoints(zoneEditingPoints.value);
  return {
    type: "FeatureCollection",
    features: midpoints.map((point, edgeIndex) => ({
      type: "Feature",
      geometry: {
        type: "Point",
        coordinates: [point.lon, point.lat],
      },
      properties: {
        edge_index: edgeIndex,
      },
    })),
  } as GeoJSON.FeatureCollection;
};

const buildZoneAreaLabelFeatureCollection = () => {
  let points: GeoPoint[] = [];
  let labelName = "";
  if (zoneMode.value && zoneDraftPoints.value.length >= 3) {
    points = zoneDraftPoints.value;
    labelName = zonePromptValue.value.trim() || "Draft Zone";
  } else if (zoneEditingId.value && zoneEditingPoints.value.length >= 3) {
    points = zoneEditingPoints.value;
    labelName = zonesStore.zoneIndex.get(zoneEditingId.value)?.name ?? "";
  } else if (selectedZone.value && selectedZone.value.points.length >= 3) {
    points = selectedZone.value.points;
    labelName = selectedZone.value.name;
  }
  if (points.length < 3) {
    return { type: "FeatureCollection", features: [] } as GeoJSON.FeatureCollection;
  }
  const centroid = polygonCentroid(points);
  if (!centroid) {
    return { type: "FeatureCollection", features: [] } as GeoJSON.FeatureCollection;
  }
  const areaLabel = formatAreaLabel(polygonAreaSquareMeters(points));
  const label = labelName ? `${labelName}\n${areaLabel}` : areaLabel;
  return {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        geometry: {
          type: "Point",
          coordinates: [centroid.lon, centroid.lat],
        },
        properties: {
          label,
        },
      },
    ],
  } as GeoJSON.FeatureCollection;
};

const addLayerWithBefore = (map: maplibregl.Map, layer: maplibregl.AddLayerObject, beforeId?: string) => {
  if (beforeId && map.getLayer(beforeId)) {
    map.addLayer(layer, beforeId);
    return;
  }
  map.addLayer(layer);
};

const renderZones = () => {
  if (!mapInstance.value || !mapReady.value) {
    return;
  }
  const map = mapInstance.value;
  const zoneSourceId = "zones";
  const zoneDraftSourceId = "zone-draft";
  const zoneHandleSourceId = "zone-handles";
  const zoneMidpointSourceId = "zone-midpoints";
  const zoneLabelSourceId = "zone-area-label";
  const beforeId = map.getLayer("operator-marker-layer") ? "operator-marker-layer" : undefined;

  const updateSource = (sourceId: string, data: GeoJSON.FeatureCollection) => {
    const existing = map.getSource(sourceId) as maplibregl.GeoJSONSource | undefined;
    if (existing) {
      existing.setData(data);
      return;
    }
    map.addSource(sourceId, { type: "geojson", data });
  };

  updateSource(zoneSourceId, buildZoneFeatureCollection());
  updateSource(zoneDraftSourceId, buildDraftZoneFeatureCollection());
  updateSource(zoneHandleSourceId, buildZoneHandleFeatureCollection());
  updateSource(zoneMidpointSourceId, buildZoneMidpointFeatureCollection());
  updateSource(zoneLabelSourceId, buildZoneAreaLabelFeatureCollection());

  if (!map.getLayer("zone-fill")) {
    addLayerWithBefore(
      map,
      {
        id: "zone-fill",
        type: "fill",
        source: zoneSourceId,
        paint: {
          "fill-color": ["case", ["==", ["get", "selected"], 1], ZONE_SELECTED_FILL_COLOR, ZONE_FILL_COLOR],
          "fill-opacity": ["case", ["==", ["get", "selected"], 1], 0.28, 0.16],
        },
      },
      beforeId
    );
  }
  if (!map.getLayer("zone-outline")) {
    addLayerWithBefore(
      map,
      {
        id: "zone-outline",
        type: "line",
        source: zoneSourceId,
        paint: {
          "line-color": ZONE_OUTLINE_COLOR,
          "line-width": ["case", ["==", ["get", "selected"], 1], 3, 2],
          "line-opacity": 0.95,
        },
      },
      beforeId
    );
  }
  if (!map.getLayer("zone-draft-fill")) {
    addLayerWithBefore(
      map,
      {
        id: "zone-draft-fill",
        type: "fill",
        source: zoneDraftSourceId,
        filter: ["==", ["geometry-type"], "Polygon"],
        paint: {
          "fill-color": "#67b8ff",
          "fill-opacity": 0.2,
        },
      },
      beforeId
    );
  }
  if (!map.getLayer("zone-draft-line")) {
    addLayerWithBefore(
      map,
      {
        id: "zone-draft-line",
        type: "line",
        source: zoneDraftSourceId,
        paint: {
          "line-color": "#8cd0ff",
          "line-width": 2.2,
          "line-dasharray": [1.2, 1.1],
        },
      },
      beforeId
    );
  }
  if (!map.getLayer("zone-handle-midpoints")) {
    map.addLayer({
      id: "zone-handle-midpoints",
      type: "circle",
      source: zoneMidpointSourceId,
      paint: {
        "circle-radius": 4,
        "circle-color": ZONE_MIDPOINT_COLOR,
        "circle-opacity": 0.95,
        "circle-stroke-color": "#09314d",
        "circle-stroke-width": 1,
      },
    });
  }
  if (!map.getLayer("zone-handle-hit")) {
    map.addLayer({
      id: "zone-handle-hit",
      type: "circle",
      source: zoneHandleSourceId,
      paint: {
        "circle-radius": 12,
        "circle-color": "#000000",
        "circle-opacity": 0,
        "circle-stroke-opacity": 0,
      },
    });
  }
  if (!map.getLayer("zone-handle-vertices")) {
    map.addLayer({
      id: "zone-handle-vertices",
      type: "circle",
      source: zoneHandleSourceId,
      paint: {
        "circle-radius": 5,
        "circle-color": ZONE_HANDLE_COLOR,
        "circle-opacity": 0.95,
        "circle-stroke-color": "#042136",
        "circle-stroke-width": 1.3,
      },
    });
  }
  if (!map.getLayer("zone-area-label")) {
    map.addLayer({
      id: "zone-area-label",
      type: "symbol",
      source: zoneLabelSourceId,
      layout: {
        "text-field": ["get", "label"],
        "text-size": 13,
        "text-font": ["Noto Sans Regular"],
        "text-anchor": "center",
        "text-allow-overlap": true,
      },
      paint: {
        "text-color": ZONE_LABEL_TEXT_COLOR,
        "text-halo-color": ZONE_LABEL_HALO_COLOR,
        "text-halo-width": 1.2,
      },
    });
  }

  if (!zoneInteractionReady) {
    map.on("click", "zone-fill", (event) => {
      if (zoneMode.value) {
        return;
      }
      const zoneId = event.features?.[0]?.properties?.id as string | undefined;
      if (!zoneId) {
        return;
      }
      selectedZoneId.value = zoneId;
      activeMarkerTab.value = "zones";
      renderZones();
    });
    map.on("contextmenu", "zone-fill", handleZoneContextMenu);
    map.on("contextmenu", "zone-outline", handleZoneContextMenu);
    map.on("mousemove", "zone-fill", (event) => {
      if (zoneMode.value || zoneEditingId.value) {
        return;
      }
      const zoneId = String(event.features?.[0]?.properties?.id ?? "").trim();
      if (!zoneId) {
        return;
      }
      openHoverZoneRadialMenu(zoneId, toScreenPoint(event.point));
    });
    map.on("mousemove", "zone-outline", (event) => {
      if (zoneMode.value || zoneEditingId.value) {
        return;
      }
      const zoneId = String(event.features?.[0]?.properties?.id ?? "").trim();
      if (!zoneId) {
        return;
      }
      openHoverZoneRadialMenu(zoneId, toScreenPoint(event.point));
    });
    map.on("mousedown", "zone-handle-hit", startZoneVertexDrag);
    map.on("mousedown", "zone-handle-vertices", startZoneVertexDrag);
    map.on("click", "zone-handle-midpoints", handleZoneMidpointClick);
    map.on("contextmenu", "zone-handle-hit", handleZoneVertexContextMenu);
    map.on("contextmenu", "zone-handle-vertices", handleZoneVertexContextMenu);
    map.on("mouseenter", "zone-fill", () => {
      map.getCanvas().style.cursor = "pointer";
    });
    map.on("mouseleave", "zone-fill", () => {
      if (zoneDraggingVertexIndex.value === null) {
        map.getCanvas().style.cursor = "";
      }
    });
    map.on("mouseenter", "zone-outline", () => {
      map.getCanvas().style.cursor = "pointer";
    });
    map.on("mouseleave", "zone-outline", () => {
      if (zoneDraggingVertexIndex.value === null) {
        map.getCanvas().style.cursor = "";
      }
    });
    map.on("mouseenter", "zone-handle-hit", () => {
      map.getCanvas().style.cursor = "move";
    });
    map.on("mouseleave", "zone-handle-hit", () => {
      if (zoneDraggingVertexIndex.value === null) {
        map.getCanvas().style.cursor = "";
      }
    });
    map.on("mouseenter", "zone-handle-vertices", () => {
      map.getCanvas().style.cursor = "move";
    });
    map.on("mouseleave", "zone-handle-vertices", () => {
      if (zoneDraggingVertexIndex.value === null) {
        map.getCanvas().style.cursor = "";
      }
    });
    map.on("mouseenter", "zone-handle-midpoints", () => {
      map.getCanvas().style.cursor = "crosshair";
    });
    map.on("mouseleave", "zone-handle-midpoints", () => {
      if (zoneDraggingVertexIndex.value === null) {
        map.getCanvas().style.cursor = "";
      }
    });
    zoneInteractionReady = true;
  }
};

const handleOperatorMarkerHoverMove = (event: maplibregl.MapLayerMouseEvent) => {
  const feature = event.features?.[0];
  const markerIdRaw = feature?.properties?.id;
  if (!markerIdRaw) {
    return;
  }
  const markerId = String(markerIdRaw);
  const anchored = resolveMarkerScreenPoint(markerId, toScreenPoint(event.point)) ?? toScreenPoint(event.point);
  if (!draggingMarkerId.value) {
    openHoverMarkerRadialMenu(markerId, anchored);
    const cursor = markerMoveArmId.value && markerMoveArmId.value === markerId ? "move" : "pointer";
    if (mapInstance.value) {
      mapInstance.value.getCanvas().style.cursor = cursor;
    }
  }
};

const handleTelemetryMarkerHoverMove = (event: maplibregl.MapLayerMouseEvent) => {
  const feature = event.features?.[0];
  const markerIdRaw = feature?.properties?.id;
  if (!markerIdRaw) {
    return;
  }
  const markerId = String(markerIdRaw);
  openHoverMarkerRadialMenu(markerId, toScreenPoint(event.point));
  if (!draggingMarkerId.value && mapInstance.value) {
    mapInstance.value.getCanvas().style.cursor = "pointer";
  }
};

const handleOperatorMarkerHoverLeave = () => {
  clearHoveredOperatorMarker();
  if (!draggingMarkerId.value && mapInstance.value) {
    mapInstance.value.getCanvas().style.cursor = "";
  }
};

const startMarkerDrag = (event: maplibregl.MapLayerMouseEvent) => {
  if (!mapInstance.value) {
    return;
  }
  const pointerEvent = event.originalEvent as MouseEvent | undefined;
  if (pointerEvent?.button !== 0) {
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
  if (!markerMoveArmId.value || markerMoveArmId.value !== marker.id) {
    return;
  }
  event.preventDefault();
  pointerEvent?.preventDefault?.();
  closeMarkerRadialMenu();
  closeMarkerCompass();
  clearHoveredOperatorMarker();
  draggingMarkerId.value = marker.id;
  draggingMarkerOrigin.value = { lat: marker.lat, lon: marker.lon };
  mapInstance.value.getCanvas().style.cursor = "grabbing";
  mapInstance.value.dragPan.disable();
  mapInstance.value.on("mousemove", handleMarkerDrag);
  mapInstance.value.once("mouseup", finishMarkerDrag);
  mapInstance.value.once("mouseleave", finishMarkerDrag);
};

const handleMarkerDrag = (event: maplibregl.MapMouseEvent) => {
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
  markerMoveArmId.value = null;
  mapInstance.value.off("mousemove", handleMarkerDrag);
  mapInstance.value.dragPan.enable();
  mapInstance.value.getCanvas().style.cursor = "";
  renderOperatorMarkers();
  syncMarkerInteractionAnchors();
  if (markerId && origin && override) {
    if (origin.lat !== override.lat || origin.lon !== override.lon) {
      void markersStore.updateMarkerPosition(markerId, override.lat, override.lon).then(() => {
        renderOperatorMarkers();
        syncMarkerInteractionAnchors();
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
  markerMoveArmId.value = null;
};

const handleOperatorMarkerContextMenu = (event: maplibregl.MapLayerMouseEvent) => {
  event.preventDefault();
  (event.originalEvent as MouseEvent | undefined)?.preventDefault?.();
  dismissRadialMenus();
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
      const geometry = feature?.geometry as GeoJSON.Point | undefined;
      const coordinates = geometry?.coordinates as [number, number] | undefined;
      if (!coordinates) {
        return;
      }
      void source
        .getClusterExpansionZoom(Number(clusterId))
        .then((zoom) => {
          map.easeTo({ center: coordinates, zoom });
        })
        .catch(() => undefined);
    });
    map.on("mouseenter", clusterLayerId, () => {
      map.getCanvas().style.cursor = "pointer";
    });
    map.on("mouseleave", clusterLayerId, () => {
      map.getCanvas().style.cursor = "";
    });
    map.on("move", () => {
      syncMarkerInteractionAnchors();
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
    map.on("mousemove", layerId, handleTelemetryMarkerHoverMove);
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
  syncMarkerInteractionAnchors();

  if (!markerInteractionReady) {
    map.on("mousedown", layerId, startMarkerDrag);
    map.on("contextmenu", layerId, handleOperatorMarkerContextMenu);
    map.on("mousemove", layerId, handleOperatorMarkerHoverMove);
    map.on("mouseleave", layerId, handleOperatorMarkerHoverLeave);
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
      const geometry = feature?.geometry as GeoJSON.Point | undefined;
      const coordinates = geometry?.coordinates as [number, number] | undefined;
      if (!coordinates) {
        return;
      }
      void source
        .getClusterExpansionZoom(Number(clusterId))
        .then((zoom) => {
          map.easeTo({ center: coordinates, zoom });
        })
        .catch(() => undefined);
    });
    map.on("mouseenter", clusterLayerId, () => {
      clearHoveredOperatorMarker();
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
  renderZones();
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

const handleMapLoaded = async (symbolsPromise: Promise<void>) => {
  mapReady.value = true;
  await symbolsPromise;
  await loadMarkerImages();
  renderMarkers();
  mapInstance.value?.on("click", handleMapClick);
  mapInstance.value?.on("contextmenu", handleMapContextMenu);
  mapInstance.value?.on("dblclick", handleMapDoubleClick);
  mapInstance.value?.on("mousemove", handleMapPointerMove);
  mapInstance.value?.on("mouseleave", handleMapPointerLeave);
  mapInstance.value?.on("zoomend", handleClusterZoom);
  mapInstance.value?.on("moveend", persistMapView);
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
    mapInstance.value.on("load", () => {
      void handleMapLoaded(symbolsPromise);
    });
  }
  await telemetry.fetchTelemetry(sinceSeconds());
  await symbolsPromise;
  await Promise.all([markersStore.fetchMarkers(), zonesStore.fetchZones()]);
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
    await Promise.all([markersStore.fetchMarkers(), zonesStore.fetchZones()]);
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
    mapInstance.value.off("contextmenu", handleMapContextMenu);
    mapInstance.value.off("dblclick", handleMapDoubleClick);
    mapInstance.value.off("mousemove", handleMapPointerMove);
    mapInstance.value.off("mouseleave", handleMapPointerLeave);
    mapInstance.value.off("mousemove", handleZoneVertexDrag);
    mapInstance.value.doubleClickZoom.enable();
  }
  window.removeEventListener("resize", handleInspectorViewportChange);
  window.removeEventListener("scroll", handleInspectorViewportChange);
  window.removeEventListener("mousedown", handleDocumentPointerDown);
  closeMarkerRadialMenu();
  closeZoneRadialMenu();
  closeZoneAssign();
  closeMarkerAssign();
  closeMarkerCompass();
  clearHoveredOperatorMarker();
  stopDrag();
  stopMarkerDrag();
});
</script>
<style scoped src="./styles/WebMapPage.css"></style>



