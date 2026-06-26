import type { TelemetryEntry } from "../api/types";
import { resolveIdentityLabel } from "./identity";

export interface TelemetryMarker {
  id: string;
  name: string;
  lat: number;
  lon: number;
  updatedAt?: string;
  topicId?: string;
  sourceType?: "telemetry" | "operator-marker";
  iconKey?: string;
  raw: TelemetryEntry;
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === "object" && !Array.isArray(value);

const isOperatorMarkerMetadata = (value: unknown) => {
  if (!isRecord(value)) {
    return false;
  }
  const objectType = value.object_type;
  if (typeof objectType === "string" && objectType.trim().toLowerCase() === "marker") {
    return true;
  }
  const eventType = value.event_type;
  if (typeof eventType === "string" && eventType.trim().toLowerCase().startsWith("marker.")) {
    return true;
  }
  return false;
};

const operatorMarkerMetadata = (entry: TelemetryEntry): Record<string, unknown> | undefined => {
  if (!isRecord(entry.data)) {
    return undefined;
  }
  const custom = entry.data.custom;
  if (!isRecord(custom)) {
    return undefined;
  }
  const candidates = [custom.marker, custom.metadata, custom];
  for (const candidate of candidates) {
    if (Array.isArray(candidate)) {
      const match = candidate.find((item) => isOperatorMarkerMetadata(item));
      if (isRecord(match)) {
        return match;
      }
      continue;
    }
    if (isOperatorMarkerMetadata(candidate)) {
      return candidate;
    }
  }
  return undefined;
};

const markerIconKey = (metadata?: Record<string, unknown>): string | undefined => {
  const value = metadata?.symbol ?? metadata?.category ?? metadata?.marker_type;
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
};

export const deriveMarkers = (entries: TelemetryEntry[]): TelemetryMarker[] => {
  return entries
    .filter(
      (entry) =>
        entry.location?.lat !== undefined &&
        entry.location?.lon !== undefined
    )
    .map((entry) => {
      const markerMetadata = operatorMarkerMetadata(entry);
      return {
        id: entry.identity_id ?? entry.identity ?? "unknown",
        name: resolveIdentityLabel(entry.display_name ?? entry.identity_label, entry.identity_id ?? entry.identity),
        lat: entry.location?.lat ?? 0,
        lon: entry.location?.lon ?? 0,
        updatedAt: entry.created_at,
        topicId: entry.topic_id,
        sourceType: markerMetadata ? "operator-marker" : "telemetry",
        iconKey: markerIconKey(markerMetadata),
        raw: entry
      };
    });
};
