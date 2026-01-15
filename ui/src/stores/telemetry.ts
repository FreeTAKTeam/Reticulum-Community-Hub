import { defineStore } from "pinia";
import { computed } from "vue";
import { ref } from "vue";
import { endpoints } from "../api/endpoints";
import { get } from "../api/client";
import type { TelemetryEntry } from "../api/types";
import { deriveMarkers } from "../utils/telemetry";
import type { TelemetryMarker } from "../utils/telemetry";

type TelemetryApiResponse = {
  entries?: TelemetryEntry[] | TelemetryApiEntry[];
};

type TelemetryApiEntry = {
  peer_destination?: string;
  timestamp?: number;
  telemetry?: Record<string, unknown>;
  topic_id?: string;
  created_at?: string;
  display_name?: string;
  identity_label?: string;
  identity_id?: string;
  identity?: string;
  id?: string;
  location?: {
    lat?: number;
    lon?: number;
    alt?: number;
  };
  data?: Record<string, unknown>;
};

const toNumber = (value: unknown) => {
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : undefined;
  }
  if (typeof value === "string") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : undefined;
  }
  return undefined;
};

const extractLocation = (telemetry?: Record<string, unknown>) => {
  if (!telemetry || typeof telemetry !== "object") {
    return undefined;
  }
  const location = (telemetry.location ?? telemetry.position ?? telemetry.geo ?? telemetry.gps) as
    | Record<string, unknown>
    | number[]
    | undefined;
  if (!location) {
    return undefined;
  }
  if (Array.isArray(location)) {
    const lat = toNumber(location[0]);
    const lon = toNumber(location[1]);
    const alt = toNumber(location[2]);
    if (lat === undefined || lon === undefined) {
      return undefined;
    }
    return { lat, lon, alt };
  }
  if (typeof location !== "object") {
    return undefined;
  }
  const lat = toNumber(location.lat ?? location.latitude ?? location.Latitude);
  const lon = toNumber(location.lon ?? location.longitude ?? location.Longitude);
  if (lat === undefined || lon === undefined) {
    return undefined;
  }
  const alt = toNumber(location.alt ?? location.altitude ?? location.Altitude);
  return { lat, lon, alt };
};

const displayNameFromTelemetry = (telemetry?: Record<string, unknown>) => {
  if (!telemetry || typeof telemetry !== "object") {
    return undefined;
  }
  const info = telemetry.information as Record<string, unknown> | string | undefined;
  if (typeof info === "string") {
    return info;
  }
  if (info && typeof info === "object") {
    const contents = info.contents;
    if (typeof contents === "string") {
      return contents;
    }
  }
  return undefined;
};

const normalizeTelemetryEntry = (entry: TelemetryEntry | TelemetryApiEntry): TelemetryEntry => {
  const raw = entry as TelemetryApiEntry;
  if (raw && (raw.telemetry || raw.peer_destination)) {
    const telemetry = raw.telemetry ?? raw.data ?? {};
    const identity = raw.peer_destination ?? raw.identity_id ?? raw.identity;
    const timestamp = typeof raw.timestamp === "number" ? raw.timestamp : undefined;
    const created_at = raw.created_at ?? (timestamp ? new Date(timestamp * 1000).toISOString() : undefined);
    const label = raw.display_name ?? raw.identity_label ?? displayNameFromTelemetry(telemetry);
    const location = raw.location ?? extractLocation(telemetry);
    const id = raw.id ?? (identity && timestamp ? `${identity}:${timestamp}` : identity ?? undefined);

    return {
      id,
      identity_id: identity,
      identity,
      display_name: label,
      identity_label: raw.identity_label ?? label,
      topic_id: raw.topic_id,
      created_at,
      location,
      data: telemetry
    };
  }
  return entry as TelemetryEntry;
};

const normalizeTelemetryEntries = (entries: Array<TelemetryEntry | TelemetryApiEntry>) =>
  entries.map(normalizeTelemetryEntry);

export const useTelemetryStore = defineStore("telemetry", () => {
  const entries = ref<TelemetryEntry[]>([]);
  const loading = ref(false);
  const topicId = ref<string>("");

  const markers = computed<TelemetryMarker[]>(() => deriveMarkers(entries.value));

  const fetchTelemetry = async (since: number) => {
    loading.value = true;
    const params = new URLSearchParams({ since: String(since) });
    if (topicId.value) {
      params.set("topic_id", topicId.value);
    }
    try {
      const response = await get<TelemetryApiResponse | TelemetryEntry[]>(
        `${endpoints.telemetry}?${params.toString()}`
      );
      const rawEntries = Array.isArray(response) ? response : response.entries ?? [];
      entries.value = normalizeTelemetryEntries(rawEntries as Array<TelemetryEntry | TelemetryApiEntry>);
    } finally {
      loading.value = false;
    }
  };

  const applySnapshot = (snapshot: Array<TelemetryEntry | TelemetryApiEntry>) => {
    entries.value = normalizeTelemetryEntries(snapshot);
  };

  const applyUpdate = (entry: TelemetryEntry | TelemetryApiEntry) => {
    const normalized = normalizeTelemetryEntry(entry);
    const key = normalized.id ?? normalized.identity_id ?? normalized.identity;
    entries.value = [
      normalized,
      ...entries.value.filter((item) => {
        const itemKey = item.id ?? item.identity_id ?? item.identity;
        return key ? itemKey !== key : item.id !== normalized.id;
      })
    ].slice(0, 200);
  };

  return {
    entries,
    loading,
    topicId,
    markers,
    fetchTelemetry,
    applySnapshot,
    applyUpdate
  };
});
