import type { TelemetryEntry } from "../api/types";
import { resolveIdentityLabel } from "./identity";

export interface TelemetryMarker {
  id: string;
  name: string;
  lat: number;
  lon: number;
  updatedAt?: string;
  topicId?: string;
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

const isOperatorMarkerEntry = (entry: TelemetryEntry) => {
  if (!isRecord(entry.data)) {
    return false;
  }
  const custom = entry.data.custom;
  if (!isRecord(custom)) {
    return false;
  }
  const marker = custom.marker;
  if (Array.isArray(marker)) {
    return marker.some((item) => isOperatorMarkerMetadata(item));
  }
  return isOperatorMarkerMetadata(marker);
};

export const deriveMarkers = (entries: TelemetryEntry[]): TelemetryMarker[] => {
  return entries
    .filter(
      (entry) =>
        entry.location?.lat !== undefined &&
        entry.location?.lon !== undefined &&
        !isOperatorMarkerEntry(entry)
    )
    .map((entry) => ({
      id: entry.identity_id ?? entry.identity ?? "unknown",
      name: resolveIdentityLabel(entry.display_name ?? entry.identity_label, entry.identity_id ?? entry.identity),
      lat: entry.location?.lat ?? 0,
      lon: entry.location?.lon ?? 0,
      updatedAt: entry.created_at,
      topicId: entry.topic_id,
      raw: entry
    }));
};
