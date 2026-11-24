import type { Feature, FeatureCollection, Point } from "geojson";

const readObject = (value: unknown): Record<string, unknown> | null =>
  value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;

const readText = (value: unknown): string => (typeof value === "string" ? value.trim() : "");

/** MECP severity, ordered 0 (Mayday) to 3 (Routine); "none" for log entries without an MECP code. */
export type MapEventSeverity = "mayday" | "urgent" | "safety" | "routine" | "none";

export const MAP_EVENT_SEVERITIES: ReadonlyArray<{ key: MapEventSeverity; label: string }> = [
  { key: "mayday", label: "Mayday" },
  { key: "urgent", label: "Urgent" },
  { key: "safety", label: "Safety" },
  { key: "routine", label: "Routine" },
  { key: "none", label: "No MECP code" }
];

const SEVERITY_BY_NUMBER: MapEventSeverity[] = ["mayday", "urgent", "safety", "routine"];
const SEVERITY_BY_STATUS: Record<string, MapEventSeverity> = { red: "mayday", yellow: "urgent", green: "safety", blue: "routine" };

const severityOf = (mecp: Record<string, unknown> | null): MapEventSeverity => {
  if (!mecp || mecp.valid !== true) return "none";
  const number = mecp.severity;
  if (typeof number === "number" && Number.isInteger(number) && SEVERITY_BY_NUMBER[number]) return SEVERITY_BY_NUMBER[number];
  return SEVERITY_BY_STATUS[readText(mecp.severity_status)] ?? "none";
};

const positionOf = (entry: Record<string, unknown> | null, mecp: Record<string, unknown> | null) => {
  const coordinates = mecp?.valid === true ? readObject(readObject(mecp.extras)?.coordinates) : null;
  const hasOwn = typeof entry?.latitude === "number" && typeof entry?.longitude === "number";
  const lat = hasOwn ? entry?.latitude : coordinates?.latitude;
  const lon = hasOwn ? entry?.longitude : coordinates?.longitude;
  if (typeof lat !== "number" || typeof lon !== "number") return null;
  if (!Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) return null;
  return { lat, lon, fromMessage: !hasOwn };
};

/**
 * Map features for events (log entries) with a position: the stored event position
 * (telemetry sent with the event), otherwise coordinates in the decoded MECP content.
 */
export function eventFeatures(entries: unknown[]): FeatureCollection<Point> {
  const features: Feature<Point>[] = [];
  for (const item of entries) {
    const entry = readObject(item);
    const mecp = readObject(entry?.mecp);
    const position = positionOf(entry, mecp);
    if (!position) continue;
    features.push({
      type: "Feature",
      geometry: { type: "Point", coordinates: [position.lon, position.lat] },
      properties: {
        uid: String(entry?.entry_uid ?? ""),
        callsign: typeof entry?.callsign === "string" ? entry.callsign : "",
        content: typeof entry?.content === "string" ? entry.content : "",
        category: typeof mecp?.category_label === "string" ? mecp.category_label : "Event",
        severity: severityOf(mecp),
        updated: typeof entry?.updated_at === "string" ? entry.updated_at : ""
      }
    });
  }
  return { type: "FeatureCollection", features };
}

export interface MapEventView {
  uid: string;
  categoryLabel: string;
  severity: { key: MapEventSeverity; label: string } | null;
  /** Decoded codes ("S01 · Need water") or, without MECP, the entry text. */
  headline: string;
  rawCode: string;
  lat: number;
  lon: number;
  locationSource: string;
  callsign: string;
  /** Sender's own clock, when the message carried one. */
  reportedAt: string;
  receivedAt: string;
  missionUid: string;
  keywords: string[];
  extras: string[];
  warnings: string[];
}

const readStrings = (value: unknown): string[] =>
  Array.isArray(value) ? value.map(readText).filter(Boolean) : [];

/** What the map event window shows for one positioned log entry; null when it has no position. */
export function presentMapEvent(item: unknown): MapEventView | null {
  const entry = readObject(item);
  const mecp = readObject(entry?.mecp);
  const position = positionOf(entry, mecp);
  if (!entry || !position) return null;
  const valid = mecp?.valid === true;
  const severityKey = severityOf(mecp);
  const codes = valid && Array.isArray(mecp?.code_details)
    ? mecp.code_details
        .map((detail) => {
          const code = readObject(detail);
          const value = readText(code?.code);
          const label = readText(code?.label);
          return label && label !== value ? `${value} · ${label}` : value;
        })
        .filter(Boolean)
    : [];
  const extras = valid ? readObject(mecp?.extras) : null;
  const extraLabels: string[] = [];
  if (typeof extras?.pax === "number") extraLabels.push(`${extras.pax} pax`);
  if (typeof extras?.eta_minutes === "number") extraLabels.push(`ETA ${extras.eta_minutes} min`);
  if (readText(extras?.language)) extraLabels.push(`Language ${readText(extras?.language)}`);
  extraLabels.push(...readStrings(extras?.references));
  return {
    uid: readText(entry.entry_uid),
    categoryLabel: valid ? readText(mecp?.category_label) || "Event" : "Log entry",
    severity: severityKey === "none" ? null : MAP_EVENT_SEVERITIES.find((item) => item.key === severityKey) ?? null,
    headline: codes.length ? codes.join(", ") : readText(entry.content),
    rawCode: valid ? readText(mecp?.raw) : "",
    lat: position.lat,
    lon: position.lon,
    locationSource: position.fromMessage ? "Coordinates in the MECP message" : "Position sent with the event",
    callsign: readText(entry.callsign) || readText(extras?.callsign),
    reportedAt: readText(entry.client_time),
    receivedAt: readText(entry.server_time) || readText(entry.created_at),
    missionUid: readText(entry.mission_uid),
    // Hide the server's own classification tags (r3akt:event-code:S01 and similar).
    keywords: readStrings(entry.keywords).filter((keyword) => !keyword.startsWith("r3akt:")),
    extras: extraLabels,
    warnings: valid ? readStrings(mecp?.warnings) : []
  };
}
