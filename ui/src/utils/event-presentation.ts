import type { EventEntry } from "../api/types";
import { isIdentityMetadataKey, resolveEventFeedMessage } from "./event-feed";

/**
 * Presentation of system events for the dashboard feed: a category, a title
 * that says who did what, a one-line summary and readable detail fields.
 * Event meaning stays with the server; this only chooses wording and layout.
 */

export type EventCategory = "messages" | "location" | "map" | "missions" | "users" | "system" | "errors" | "transport";

export interface EventDetail {
  label: string;
  value: string;
  /** Monospace part shown after the value, e.g. an address next to a name. */
  mono?: string;
}

export interface PresentedEvent {
  category: EventCategory;
  title: string;
  summary: string;
  details: EventDetail[];
  /** Broker bookkeeping, hidden unless transport internals are shown. */
  transport: boolean;
}

export interface EventNameLookups {
  /** Callsign or user name for an identity / destination hash (lower-case keys). */
  identities: ReadonlyMap<string, string>;
  /** Mission name by mission UID. */
  missions?: ReadonlyMap<string, string>;
}

type Metadata = Record<string, unknown>;

const text = (value: unknown): string =>
  typeof value === "string" ? value.trim() : typeof value === "number" || typeof value === "boolean" ? String(value) : "";

const shortHash = (value: string): string =>
  /^[0-9a-f]{20,}$/i.test(value) ? `${value.slice(0, 8)}…${value.slice(-8)}` : value;

const humanize = (value: string): string => {
  const spaced = value.replace(/[_.]+/g, " ").replace(/([a-z])([A-Z])/g, "$1 $2").trim().toLowerCase();
  return spaced ? `${spaced.charAt(0).toUpperCase()}${spaced.slice(1)}` : "";
};

const type = (event: EventEntry): string => text(event.category);

export const eventCategory = (event: EventEntry): EventCategory => {
  const kind = type(event).toLowerCase();
  const level = text(event.level).toLowerCase();
  // Broker bookkeeping, and the telemetry copy recorded for every marker change.
  if (kind === "durable_broker_handled" || kind === "marker_telemetry_recorded") return "transport";
  if (
    level === "error" ||
    level === "critical" ||
    /(^lxmf_.*_diagnostic$|_failed$|_error$|_timeout$)/.test(kind)
  ) {
    return "errors";
  }
  if (kind.startsWith("message")) return "messages";
  if (kind.startsWith("mission")) return "missions";
  if (kind.startsWith("marker") || kind.startsWith("zone")) return "map";
  if (kind.startsWith("telemetry")) return "location";
  if (kind.includes("identity") || kind.startsWith("client") || kind.startsWith("peer") || kind.startsWith("rem")) {
    return "users";
  }
  return "system";
};

const nameFor = (identity: string, lookups: EventNameLookups): string => {
  const key = identity.trim().toLowerCase();
  return key ? lookups.identities.get(key) ?? shortHash(key) : "";
};

const facts = (...parts: Array<string | false | undefined>): string =>
  parts.filter((part): part is string => Boolean(part && part.trim())).join(" · ");

const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? "" : "s"}`;

/** How a message travels, in operator terms; the internal broker path is not worth showing. */
const DELIVERY_METHODS: Record<string, string> = {
  direct: "Direct",
  propagated: "Via propagation node",
  opportunistic: "Opportunistic",
  durable_broker: ""
};
const deliveryMethod = (value: string) => (value in DELIVERY_METHODS ? DELIVERY_METHODS[value] : humanize(value));

const titleAndSummary = (
  event: EventEntry,
  metadata: Metadata,
  lookups: EventNameLookups
): { title: string; summary: string } | null => {
  const kind = type(event);
  const message = text(event.message);
  const peer = (key: string) => nameFor(text(metadata[key]), lookups);
  const topic = text(metadata.topic_id ?? metadata.topic);
  const missionName = () => {
    const uid = text(metadata.mission_uid);
    return lookups.missions?.get(uid) ?? (uid ? shortHash(uid) : "a mission");
  };

  switch (kind) {
    case "durable_broker_handled": {
      const step = message.toLowerCase();
      if (step === "inbound" || step === "bootstrap_message") {
        return { title: "Inbound LXMF message processed", summary: facts(peer("source") && `from ${peer("source")}`) };
      }
      if (step === "outbound") {
        return { title: "Outbound delivery queued", summary: facts(peer("destination") && `to ${peer("destination")}`) };
      }
      if (step === "receipt") {
        return {
          title: "Delivery receipt processed",
          summary: facts(peer("destination") && `for ${peer("destination")}`, text(metadata.status) && humanize(text(metadata.status)))
        };
      }
      return { title: `Transport step: ${humanize(message) || "unknown"}`, summary: "" };
    }
    case "lxmf_command_diagnostic":
      return { title: peer("source") ? `Unsupported command from ${peer("source")}` : "Unsupported LXMF command", summary: message };
    case "lxmf_telemetry_diagnostic":
      return { title: peer("source") ? `Unreadable telemetry from ${peer("source")}` : "Unreadable telemetry", summary: message };
    case "telemetry_request": {
      const to = peer("peer");
      const status = text(metadata.status);
      if (status) {
        return { title: to ? `Telemetry request from ${to}: ${humanize(status).toLowerCase()}` : `Telemetry request ${humanize(status).toLowerCase()}`, summary: message };
      }
      const count = Number(metadata.entry_count);
      const unavailable = Number(metadata.unavailable_records);
      return {
        title: to ? `Telemetry snapshot sent to ${to}` : "Telemetry snapshot sent",
        summary: facts(
          Number.isFinite(count) && `${count} ${count === 1 ? "entry" : "entries"}`,
          Number.isFinite(unavailable) && unavailable > 0 && `${unavailable} unavailable`
        )
      };
    }
    case "message_sent": {
      const to = peer("destination");
      return {
        title: to ? `Message sent to ${to}` : topic ? `Message sent to topic ${topic}` : "Broadcast message sent",
        summary: facts(to && topic && `topic ${topic}`, deliveryMethod(text(metadata.delivery_method)), text(metadata.delivery_state) && humanize(text(metadata.delivery_state)))
      };
    }
    case "message_failed":
    case "message_delivery_failed": {
      const to = peer("destination");
      const reason = text(metadata.drop_reason ?? metadata.reason ?? metadata.error);
      return {
        title: to ? `Message to ${to} failed` : topic ? `Message to topic ${topic} failed` : "Broadcast message failed",
        summary: facts(reason && humanize(reason), to && topic && `topic ${topic}`)
      };
    }
    case "message_received":
      return { title: resolveEventFeedMessage(event, lookups.identities), summary: facts(topic && `topic ${topic}`) };
    case "IdentityAnnounceRecorded": {
      const name = text(metadata.display_name) || peer("identity") || peer("destination_hash");
      return {
        title: name ? `${name} announced` : "Identity announced",
        summary: facts(text(metadata.source_interface) && `via ${text(metadata.source_interface)}`)
      };
    }
    case "mission.registry.mission.marker.linked":
    case "mission.registry.mission.marker.unlinked":
    case "mission.registry.mission.zone.linked":
    case "mission.registry.mission.zone.unlinked": {
      const object = kind.includes(".zone.") ? "Zone" : "Marker";
      const linked = kind.endsWith(".linked");
      const fanout = Number(metadata.recipient_fanout);
      return {
        title: `${object} ${linked ? "linked to" : "removed from"} mission ${missionName()}`,
        summary: facts(Number.isFinite(fanout) && fanout > 0 && `${plural(fanout, "recipient")} notified`)
      };
    }
    case "mission.registry.mission_change.upserted":
      return { title: `Mission updated: ${missionName()}`, summary: message };
    case "control_announce_requested":
      return { title: "Operator requested a hub announce", summary: "" };
    case "control_start_requested":
    case "control_stop_requested":
    case "control_sync_requested":
      return { title: `Operator requested ${kind.split("_")[1]}`, summary: "" };
    case "control_sync_timeout":
      return { title: "Propagation sync timed out", summary: message };
    case "identity_announce_error":
      return { title: "Hub announce failed", summary: text(metadata.exception_message) || message };
    case "telemetry_error":
      return { title: "Telemetry snapshot could not be recorded", summary: text(metadata.error ?? metadata.exception_message) };
    default:
      return null;
  }
};

const SUMMARY_KEYS: Array<[string, (value: string) => string]> = [
  ["topic_id", (value) => `topic ${value}`],
  ["topic", (value) => `topic ${value}`],
  ["delivery_state", humanize],
  ["status", humanize],
  ["drop_reason", humanize],
  ["exception_message", (value) => value],
  ["error", (value) => value]
];

const defaultSummary = (metadata: Metadata): string => {
  const parts = SUMMARY_KEYS.map(([key, format]) => (text(metadata[key]) ? format(text(metadata[key])) : "")).filter(Boolean);
  const lat = Number(metadata.lat);
  const lon = Number(metadata.lon);
  if (Number.isFinite(lat) && Number.isFinite(lon) && metadata.lat !== undefined) {
    parts.push(`${lat.toFixed(4)}, ${lon.toFixed(4)}`);
  }
  return facts(...parts.slice(0, 3));
};

const DETAIL_SKIP = new Set(["position_lat", "position_lon", "dedupe_key"]);

/** Flat, readable metadata fields; identities show the name with the address beside it. */
export const eventDetails = (metadata: Metadata, lookups: EventNameLookups, limit = 12): EventDetail[] => {
  const details: EventDetail[] = [];
  const visit = (value: unknown, path: string[]) => {
    if (details.length >= limit || value === null || value === undefined) return;
    const key = path[path.length - 1] ?? "";
    const flatKey = path.join("_");
    if (DETAIL_SKIP.has(flatKey)) return;
    if (Array.isArray(value)) {
      const items = value.map(text).filter(Boolean);
      if (items.length && items.length === value.length) details.push({ label: humanize(flatKey), value: items.join(", ") });
      return;
    }
    if (typeof value === "object") {
      if (path.length >= 2) return;
      Object.entries(value as Metadata).forEach(([child, entry]) => visit(entry, [...path, child]));
      return;
    }
    const raw = text(value);
    if (!raw) return;
    if (isIdentityMetadataKey(key) && /^[0-9a-f]{16,}$/i.test(raw)) {
      const name = lookups.identities.get(raw.toLowerCase());
      details.push({ label: humanize(flatKey), value: name ? `${name} ` : "", mono: shortHash(raw) });
      return;
    }
    if (key === "mission_uid" && lookups.missions?.get(raw)) {
      details.push({ label: "Mission", value: `${lookups.missions.get(raw)} `, mono: shortHash(raw) });
      return;
    }
    const looksLikeId = /(^|_)(id|uid|hash)$/.test(key) || /^[0-9a-f]{20,}$/i.test(raw);
    details.push(looksLikeId ? { label: humanize(flatKey), value: "", mono: shortHash(raw) } : { label: humanize(flatKey), value: raw });
  };
  Object.entries(metadata).forEach(([key, value]) => visit(value, [key]));
  return details;
};

export const presentEvent = (event: EventEntry, lookups: EventNameLookups): PresentedEvent => {
  const metadata = (event.metadata ?? {}) as Metadata;
  const category = eventCategory(event);
  const specific = titleAndSummary(event, metadata, lookups);
  const resolved = resolveEventFeedMessage(event, lookups.identities);
  // A bare type token ("receipt", "mission.joined") reads better humanized.
  const fallbackTitle = /^[a-z0-9_.]+$/.test(resolved) ? humanize(resolved) : resolved;
  return {
    category,
    title: specific?.title || fallbackTitle || humanize(type(event)) || "Event",
    summary: specific ? specific.summary : defaultSummary(metadata),
    details: eventDetails(metadata, lookups),
    transport: category === "transport"
  };
};
