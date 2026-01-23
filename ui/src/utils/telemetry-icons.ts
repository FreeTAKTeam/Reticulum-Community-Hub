import type { TelemetryEntry } from "../api/types";

import mdiAlert from "@mdi/svg/svg/alert.svg?raw";
import mdiAntenna from "@mdi/svg/svg/antenna.svg?raw";
import mdiCamera from "@mdi/svg/svg/camera.svg?raw";
import mdiCar from "@mdi/svg/svg/car.svg?raw";
import mdiClipboardCheck from "@mdi/svg/svg/clipboard-check.svg?raw";
import mdiDrone from "@mdi/svg/svg/drone.svg?raw";
import mdiFire from "@mdi/svg/svg/fire.svg?raw";
import mdiFlood from "@mdi/svg/svg/home-flood.svg?raw";
import mdiGroup from "@mdi/svg/svg/account-group.svg?raw";
import mdiHospital from "@mdi/svg/svg/hospital.svg?raw";
import mdiInfrastructure from "@mdi/svg/svg/office-building.svg?raw";
import mdiMarker from "@mdi/svg/svg/map-marker.svg?raw";
import mdiPerson from "@mdi/svg/svg/account.svg?raw";
import mdiRadio from "@mdi/svg/svg/radio.svg?raw";
import mdiRadar from "@mdi/svg/svg/radar.svg?raw";
import mdiPaw from "@mdi/svg/svg/paw.svg?raw";

export type TelemetryIconKey =
  | "marker"
  | "vehicle"
  | "drone"
  | "animal"
  | "sensor"
  | "radio"
  | "antenna"
  | "camera"
  | "fire"
  | "flood"
  | "person"
  | "group"
  | "infrastructure"
  | "medic"
  | "alert"
  | "task";

export type TelemetryIconDefinition = {
  key: TelemetryIconKey;
  label: string;
  svg: string;
};

const TELEMETRY_ICONS: Record<TelemetryIconKey, TelemetryIconDefinition> = {
  marker: { key: "marker", label: "Marker", svg: mdiMarker },
  vehicle: { key: "vehicle", label: "Vehicle", svg: mdiCar },
  drone: { key: "drone", label: "Drone", svg: mdiDrone },
  animal: { key: "animal", label: "Animal", svg: mdiPaw },
  sensor: { key: "sensor", label: "Sensor", svg: mdiRadar },
  radio: { key: "radio", label: "Radio", svg: mdiRadio },
  antenna: { key: "antenna", label: "Antenna", svg: mdiAntenna },
  camera: { key: "camera", label: "Camera", svg: mdiCamera },
  fire: { key: "fire", label: "Fire", svg: mdiFire },
  flood: { key: "flood", label: "Flood", svg: mdiFlood },
  person: { key: "person", label: "Person", svg: mdiPerson },
  group: { key: "group", label: "Group / Community", svg: mdiGroup },
  infrastructure: { key: "infrastructure", label: "Infrastructure", svg: mdiInfrastructure },
  medic: { key: "medic", label: "Medic", svg: mdiHospital },
  alert: { key: "alert", label: "Alert", svg: mdiAlert },
  task: { key: "task", label: "Task", svg: mdiClipboardCheck }
};

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

export const telemetryIcons = Object.values(TELEMETRY_ICONS);
const TELEMETRY_ICON_KEYS = new Set<TelemetryIconKey>(telemetryIcons.map((icon) => icon.key));

export const telemetryIconOptions = telemetryIcons.map((icon) => ({
  label: icon.label,
  value: icon.key
}));

export const buildTelemetryIconId = (key: TelemetryIconKey) => `mdi-${key}`;

export const isTelemetryIconKey = (value?: string): value is TelemetryIconKey => {
  if (!value) {
    return false;
  }
  return TELEMETRY_ICON_KEYS.has(value as TelemetryIconKey);
};

const normalizeKey = (value: string) => {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
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

export const resolveTelemetryIconKey = (entry: TelemetryEntry): TelemetryIconKey => {
  const data = entry.data;
  if (!data || typeof data !== "object") {
    return "marker";
  }
  const raw = pickTelemetryField(data as Record<string, unknown>);
  if (!raw) {
    return "marker";
  }
  const normalized = normalizeKey(raw);
  return TELEMETRY_ICON_ALIASES[normalized] ?? "marker";
};
