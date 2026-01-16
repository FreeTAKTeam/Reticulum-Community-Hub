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

export const deriveMarkers = (entries: TelemetryEntry[]): TelemetryMarker[] => {
  return entries
    .filter((entry) => entry.location?.lat !== undefined && entry.location?.lon !== undefined)
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
