import type { TelemetryEntry } from "../api/types";

export type TelemetryIconKey = string;

const TELEMETRY_ICON_ALIASES: Record<string, TelemetryIconKey> = {
  marker: "marker",
  pin: "marker",
  location: "marker",
  vehicle: "vehicle",
  car: "vehicle",
  truck: "vehicle",
  auto: "vehicle",
  automobile: "vehicle",
  drone: "drone",
  uav: "drone",
  uas: "drone",
  animal: "animal",
  wildlife: "animal",
  pet: "animal",
  sensor: "sensor",
  radar: "sensor",
  telemetry: "sensor",
  "vehicle-sensor": "sensor",
  radio: "radio",
  antenna: "antenna",
  camera: "camera",
  cctv: "camera",
  fire: "fire",
  flame: "fire",
  wildfire: "fire",
  flood: "flood",
  water: "flood",
  person: "person",
  human: "person",
  operator: "person",
  group: "group",
  community: "group",
  "group-community": "group",
  team: "group",
  infrastructure: "infrastructure",
  building: "infrastructure",
  facility: "infrastructure",
  medic: "medic",
  medical: "medic",
  hospital: "medic",
  alert: "alert",
  alarm: "alert",
  warning: "alert",
  task: "task",
  mission: "task",
  assignment: "task"
};

export const buildTelemetryIconId = (key: TelemetryIconKey) => `mdi-${key}`;

const normalizeSegment = (value: string) =>
  value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");

export const normalizeTelemetryIconKey = (value: string) => {
  const parts = value.split(".").map(normalizeSegment).filter((part) => part);
  return parts.join(".");
};

export const resolveTelemetryIconValue = (value: string, validKeys?: Set<string>): TelemetryIconKey => {
  if (!value) {
    return "marker";
  }
  const normalized = normalizeTelemetryIconKey(value);
  const resolved = TELEMETRY_ICON_ALIASES[normalized] ?? normalized;
  if (validKeys && !validKeys.has(resolved)) {
    return "marker";
  }
  return resolved || "marker";
};

const pickTelemetryField = (data: Record<string, unknown>) => {
  const candidates = [
    data.telemetry_type,
    data.icon,
    data.symbol,
    data.category,
    data.type,
    data.kind,
    data.role,
    data.class
  ];
  for (const candidate of candidates) {
    if (typeof candidate === "string" && candidate.trim()) {
      return candidate;
    }
  }
  return undefined;
};

export const resolveTelemetryIconKey = (entry: TelemetryEntry, validKeys?: Set<string>): TelemetryIconKey => {
  const data = entry.data;
  if (!data || typeof data !== "object") {
    return "marker";
  }
  const raw = pickTelemetryField(data as Record<string, unknown>);
  if (!raw) {
    return "marker";
  }
  return resolveTelemetryIconValue(raw, validKeys);
};
