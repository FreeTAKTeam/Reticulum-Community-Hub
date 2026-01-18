import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { endpoints } from "../api/endpoints";
import { get } from "../api/client";
import { patch } from "../api/client";
import { post } from "../api/client";
import type { MarkerEntry } from "../api/types";
import { getMarkerSymbol } from "../utils/markers";

export type Marker = {
  id: string;
  type: string;
  name: string;
  category: string;
  notes?: string | null;
  lat: number;
  lon: number;
  createdAt?: string;
  updatedAt?: string;
  color?: string;
};

export type MarkerCreatePayload = {
  name?: string;
  category: string;
  lat: number;
  lon: number;
  notes?: string | null;
};

type MarkerCreateResponse = {
  marker_id?: string;
  created_at?: string;
};

const fallbackMarkerId = () => {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `marker-${Math.random().toString(16).slice(2, 10)}`;
};

const fromApiMarker = (entry: MarkerEntry): Marker | null => {
  if (!entry.marker_id || !entry.position) {
    return null;
  }
  const category = entry.category ?? "marker";
  const symbol = getMarkerSymbol(category);
  return {
    id: entry.marker_id,
    type: entry.type ?? symbol?.set ?? "custom",
    name: entry.name ?? category,
    category,
    notes: entry.notes ?? null,
    lat: entry.position.lat ?? 0,
    lon: entry.position.lon ?? 0,
    createdAt: entry.created_at,
    updatedAt: entry.updated_at,
    color: symbol?.color
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

  const createMarker = async (payload: MarkerCreatePayload) => {
    const response = await post<MarkerCreateResponse>(endpoints.markers, payload);
    const symbol = getMarkerSymbol(payload.category);
    const created: Marker = {
      id: response.marker_id ?? fallbackMarkerId(),
      type: symbol?.set ?? "custom",
      name: payload.name ?? payload.category,
      category: payload.category,
      notes: payload.notes ?? null,
      lat: payload.lat,
      lon: payload.lon,
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

  return {
    markers,
    loading,
    markerIndex,
    fetchMarkers,
    createMarker,
    updateMarkerPosition
  };
});
