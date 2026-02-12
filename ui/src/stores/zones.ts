import { defineStore } from "pinia";
import { computed } from "vue";
import { ref } from "vue";
import { del } from "../api/client";
import { get } from "../api/client";
import { patch } from "../api/client";
import { post } from "../api/client";
import { endpoints } from "../api/endpoints";
import type { ZoneEntry } from "../api/types";
import type { ZonePoint } from "../api/types";

export type Zone = {
  id: string;
  name: string;
  points: Array<{ lat: number; lon: number }>;
  createdAt?: string;
  updatedAt?: string;
};

type ZoneCreateResponse = {
  zone_id?: string;
  created_at?: string;
};

type ZoneUpdateResponse = {
  status?: string;
  updated_at?: string;
};

type ZoneDeleteResponse = {
  status?: string;
  deleted_at?: string;
};

const fallbackZoneId = () => {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `zone-${Math.random().toString(16).slice(2, 10)}`;
};

const normalizePoints = (points?: ZonePoint[]) => {
  const normalized: Array<{ lat: number; lon: number }> = [];
  (points ?? []).forEach((point) => {
    const lat = point?.lat;
    const lon = point?.lon;
    if (typeof lat !== "number" || !Number.isFinite(lat)) {
      return;
    }
    if (typeof lon !== "number" || !Number.isFinite(lon)) {
      return;
    }
    normalized.push({ lat, lon });
  });
  return normalized;
};

const fromApiZone = (entry: ZoneEntry): Zone | null => {
  const zoneId = entry.zone_id;
  const name = (entry.name ?? "").trim();
  const points = normalizePoints(entry.points);
  if (!zoneId || !name || points.length < 3) {
    return null;
  }
  return {
    id: zoneId,
    name,
    points,
    createdAt: entry.created_at,
    updatedAt: entry.updated_at,
  };
};

export const useZonesStore = defineStore("zones", () => {
  const zones = ref<Zone[]>([]);
  const loading = ref(false);

  const zoneIndex = computed(() => {
    const map = new Map<string, Zone>();
    zones.value.forEach((zone) => {
      map.set(zone.id, zone);
    });
    return map;
  });

  const fetchZones = async () => {
    loading.value = true;
    try {
      const response = await get<ZoneEntry[]>(endpoints.zones);
      zones.value = response.map(fromApiZone).filter((zone): zone is Zone => zone !== null);
    } finally {
      loading.value = false;
    }
  };

  const createZone = async (payload: { name: string; points: Array<{ lat: number; lon: number }> }) => {
    const response = await post<ZoneCreateResponse>(endpoints.zones, payload);
    const now = new Date().toISOString();
    const created: Zone = {
      id: response.zone_id ?? fallbackZoneId(),
      name: payload.name.trim(),
      points: payload.points.map((point) => ({ lat: point.lat, lon: point.lon })),
      createdAt: response.created_at ?? now,
      updatedAt: response.created_at ?? now,
    };
    zones.value = [...zones.value, created];
    return created;
  };

  const updateZone = async (
    zoneId: string,
    payload: { name?: string; points?: Array<{ lat: number; lon: number }> }
  ) => {
    const body: Record<string, unknown> = {};
    if (payload.name !== undefined) {
      body.name = payload.name;
    }
    if (payload.points !== undefined) {
      body.points = payload.points;
    }
    const response = await patch<ZoneUpdateResponse>(`${endpoints.zones}/${zoneId}`, body);
    const updatedAt = response.updated_at ?? new Date().toISOString();
    zones.value = zones.value.map((zone) => {
      if (zone.id !== zoneId) {
        return zone;
      }
      return {
        ...zone,
        name: payload.name !== undefined ? payload.name.trim() : zone.name,
        points:
          payload.points !== undefined
            ? payload.points.map((point) => ({ lat: point.lat, lon: point.lon }))
            : zone.points,
        updatedAt,
      };
    });
    return response;
  };

  const deleteZone = async (zoneId: string) => {
    const response = await del<ZoneDeleteResponse>(`${endpoints.zones}/${zoneId}`);
    zones.value = zones.value.filter((zone) => zone.id !== zoneId);
    return response;
  };

  return {
    zones,
    loading,
    zoneIndex,
    fetchZones,
    createZone,
    updateZone,
    deleteZone,
  };
});
