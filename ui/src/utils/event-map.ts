import type { Feature, FeatureCollection, Point } from "geojson";

const readObject = (value: unknown): Record<string, unknown> | null =>
  value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;

/**
 * Map features for events (log entries) with a position: the stored event position
 * (telemetry sent with the event), otherwise coordinates in the decoded MECP content.
 */
export function eventFeatures(entries: unknown[]): FeatureCollection<Point> {
  const features: Feature<Point>[] = [];
  for (const item of entries) {
    const entry = readObject(item);
    const mecp = readObject(entry?.mecp);
    const coordinates = mecp?.valid === true ? readObject(readObject(mecp.extras)?.coordinates) : null;
    const hasOwn = typeof entry?.latitude === "number" && typeof entry?.longitude === "number";
    const lat = hasOwn ? entry?.latitude : coordinates?.latitude;
    const lon = hasOwn ? entry?.longitude : coordinates?.longitude;
    if (typeof lat !== "number" || typeof lon !== "number") continue;
    if (!Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) continue;
    features.push({
      type: "Feature",
      geometry: { type: "Point", coordinates: [lon, lat] },
      properties: {
        uid: String(entry?.entry_uid ?? ""),
        callsign: typeof entry?.callsign === "string" ? entry.callsign : "",
        content: typeof entry?.content === "string" ? entry.content : "",
        category: typeof mecp?.category_label === "string" ? mecp.category_label : "Event",
        severity: typeof mecp?.severity_status === "string" ? mecp.severity_status : "unknown",
        updated: typeof entry?.updated_at === "string" ? entry.updated_at : ""
      }
    });
  }
  return { type: "FeatureCollection", features };
}
