import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { endpoints } from "../api/endpoints";
import { get } from "../api/client";
import { patch } from "../api/client";
import { post } from "../api/client";
import type { MarkerEntry } from "../api/types";
import type { MarkerSymbolEntry } from "../api/types";
import type { MarkerSymbolSet } from "../utils/markers";
import { buildMarkerSymbols } from "../utils/markers";
import { getMarkerSymbol } from "../utils/markers";
import { normalizeMarkerSymbolSet } from "../utils/markers";
import { setMarkerSymbols } from "../utils/markers";

export type Marker = {
  id: string;
  objectDestinationHash?: string;
  originRch?: string;
  type: string;
  name: string;
  category: string;
  symbol: string;
  symbolSet?: MarkerSymbolSet;
  notes?: string | null;
  lat: number;
  lon: number;
  time?: string;
  staleAt?: string;
  createdAt?: string;
  updatedAt?: string;
  color?: string;
  expired?: boolean;
};

export type MarkerCreatePayload = {
  name?: string;
  type: string;
  symbol: string;
  category: string;
  lat: number;
  lon: number;
  notes?: string | null;
};

type MarkerCreateResponse = {
  object_destination_hash?: string;
  created_at?: string;
};

const fallbackMarkerId = () => {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `marker-${Math.random().toString(16).slice(2, 10)}`;
};

const fromApiMarker = (entry: MarkerEntry): Marker | null => {
  if (!entry.position) {
    return null;
  }
  const objectHash = entry.object_destination_hash ?? entry.marker_id ?? "";
  if (!objectHash) {
    return null;
  }
  const symbolId = entry.symbol ?? entry.type ?? entry.category ?? "marker";
  const category = entry.category ?? symbolId;
  const categorySet = normalizeMarkerSymbolSet(category);
  const symbol = getMarkerSymbol(symbolId, categorySet);
  const symbolSet = symbol?.set ?? categorySet;
  const staleAt = entry.stale_at ?? undefined;
  const expired = staleAt ? new Date(staleAt).getTime() < Date.now() : false;
  return {
    id: objectHash,
    objectDestinationHash: entry.object_destination_hash,
    originRch: entry.origin_rch,
    type: entry.type ?? symbolId,
    name: entry.name ?? category,
    category,
    symbol: symbolId,
    symbolSet,
    notes: entry.notes ?? null,
    lat: entry.position.lat ?? 0,
    lon: entry.position.lon ?? 0,
    time: entry.time ?? entry.updated_at ?? entry.created_at,
    staleAt,
    createdAt: entry.created_at,
    updatedAt: entry.updated_at,
    color: symbol?.color,
    expired
  };
};

export const useMarkersStore = defineStore("markers", () => {
  const markers = ref<Marker[]>([]);
  const loading = ref(false);

  const markerIndex = computed(() => {
    const index = new Map<string, Marker>();
    markers.value.forEach((marker) => {
      index.set(marker.id, marker);
    });
    return index;
  });

  const fetchMarkers = async () => {
    loading.value = true;
    try {
      const response = await get<MarkerEntry[]>(endpoints.markers);
      markers.value = response.map(fromApiMarker).filter((item): item is Marker => item !== null);
    } finally {
      loading.value = false;
    }
  };

  const fetchMarkerSymbols = async () => {
    const response = await get<MarkerSymbolEntry[]>(endpoints.markerSymbols);
    const symbols = buildMarkerSymbols(response);
    setMarkerSymbols(symbols);
    return symbols;
  };

  const createMarker = async (payload: MarkerCreatePayload) => {
    const response = await post<MarkerCreateResponse>(endpoints.markers, payload);
    const symbolSet = normalizeMarkerSymbolSet(payload.category);
    const symbol = getMarkerSymbol(payload.symbol, symbolSet);
    const created: Marker = {
      id: response.object_destination_hash ?? fallbackMarkerId(),
      objectDestinationHash: response.object_destination_hash,
      type: payload.type,
      name: payload.name ?? payload.category,
      category: payload.category,
      symbol: payload.symbol,
      symbolSet: symbol?.set ?? symbolSet,
      notes: payload.notes ?? null,
      lat: payload.lat,
      lon: payload.lon,
      time: new Date().toISOString(),
      staleAt: undefined,
      createdAt: response.created_at ?? new Date().toISOString(),
      updatedAt: response.created_at ?? new Date().toISOString(),
      color: symbol?.color
    };
    markers.value = [...markers.value, created];
    return created;
  };

  const updateMarkerPosition = async (markerId: string, lat: number, lon: number) => {
    await patch(`${endpoints.markers}/${markerId}/position`, { lat, lon });
    const updatedAt = new Date().toISOString();
    markers.value = markers.value.map((marker) =>
      marker.id === markerId ? { ...marker, lat, lon, updatedAt } : marker
    );
  };

  const updateMarkerName = async (markerId: string, name: string) => {
    const trimmed = name.trim();
    if (!trimmed) {
      throw new Error("Marker name is required");
    }
    try {
      await patch(`${endpoints.markers}/${markerId}`, { name: trimmed });
    } catch {
      // Keep optimistic local rename when the backend does not support this route.
    }
    const updatedAt = new Date().toISOString();
    markers.value = markers.value.map((marker) =>
      marker.id === markerId ? { ...marker, name: trimmed, updatedAt } : marker
    );
  };

  return {
    markers,
    loading,
    markerIndex,
    fetchMarkerSymbols,
    fetchMarkers,
    createMarker,
    updateMarkerPosition,
    updateMarkerName
  };
});
