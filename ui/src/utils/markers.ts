import { computed } from "vue";
import { ref } from "vue";
import type { MarkerSymbolEntry } from "../api/types";

export type MarkerSymbolSet = "napsg" | "mdi";

export type MarkerSymbol = {
  id: string;
  label: string;
  set: MarkerSymbolSet;
  color: string;
  mdi?: string;
};

const NAPSG_COLORS = ["#F97316", "#FACC15", "#EF4444", "#60A5FA", "#FBBF24", "#34D399"];
const MDI_COLORS = ["#38BDF8", "#A78BFA", "#F59E0B", "#F87171", "#22D3EE", "#94A3B8"];
const EXPLICIT_SYMBOL_COLORS: Record<string, string> = {
  friendly: "#6BCBEC",
  hostile: "#DE6767",
  neutral: "#9BBB59",
  unknown: "#F1E097"
};

const FALLBACK_SYMBOLS: MarkerSymbol[] = [
  { id: "marker", label: "Marker", set: "mdi", color: "#38BDF8", mdi: "map-marker" },
  { id: "friendly", label: "Friendly", set: "mdi", color: "#6BCBEC", mdi: "rectangle" },
  { id: "hostile", label: "Hostile", set: "mdi", color: "#DE6767", mdi: "rhombus" },
  { id: "neutral", label: "Neutral", set: "mdi", color: "#9BBB59", mdi: "square" },
  { id: "unknown", label: "Unknown", set: "mdi", color: "#F1E097", mdi: "clover" },
  { id: "vehicle", label: "Vehicle", set: "mdi", color: "#A78BFA", mdi: "car" },
  { id: "drone", label: "Drone", set: "mdi", color: "#F59E0B", mdi: "drone" },
  { id: "animal", label: "Animal", set: "mdi", color: "#F87171", mdi: "paw" },
  { id: "sensor", label: "Sensor", set: "mdi", color: "#22D3EE", mdi: "radar" },
  { id: "radio", label: "Radio", set: "mdi", color: "#94A3B8", mdi: "radio" },
  { id: "antenna", label: "Antenna", set: "mdi", color: "#38BDF8", mdi: "antenna" },
  { id: "camera", label: "Camera", set: "mdi", color: "#A78BFA", mdi: "camera" },
  { id: "fire", label: "Fire", set: "mdi", color: "#F59E0B", mdi: "fire" },
  { id: "flood", label: "Flood", set: "mdi", color: "#F87171", mdi: "home-flood" },
  { id: "person", label: "Person", set: "mdi", color: "#22D3EE", mdi: "account" },
  { id: "group", label: "Group / Community", set: "mdi", color: "#94A3B8", mdi: "account-group" },
  { id: "infrastructure", label: "Infrastructure", set: "mdi", color: "#38BDF8", mdi: "office-building" },
  { id: "medic", label: "Medic", set: "mdi", color: "#A78BFA", mdi: "hospital" },
  { id: "alert", label: "Alert", set: "mdi", color: "#F59E0B", mdi: "alert" },
  { id: "task", label: "Task", set: "mdi", color: "#F87171", mdi: "clipboard-check" }
];

const FALLBACK_SYMBOL_MAP = new Map(
  FALLBACK_SYMBOLS.map((symbol) => [symbol.id, symbol])
);

export const normalizeMarkerSymbolSet = (value?: string): MarkerSymbolSet | undefined => {
  const normalized = value?.toLowerCase();
  if (normalized === "napsg" || normalized === "mdi") {
    return normalized;
  }
  return undefined;
};

export const buildMarkerSymbolKey = (set: MarkerSymbolSet, id: string) => `${set}:${id}`;

export const parseMarkerSymbolKey = (value: string) => {
  const parts = value.split(":");
  const maybeSet = normalizeMarkerSymbolSet(parts[0]);
  if (maybeSet && parts.length > 1) {
    return { set: maybeSet, id: parts.slice(1).join(":") };
  }
  return { set: undefined, id: value };
};

const titleizeSymbol = (value: string) =>
  value
    .split(/[-.]+/)
    .filter((segment) => segment)
    .map((segment) => segment[0]?.toUpperCase() + segment.slice(1))
    .join(" ");

const symbolLabel = (id: string, set: MarkerSymbolSet) => {
  if (set === "mdi") {
    return titleizeSymbol(id);
  }
  const setLabel = set.toUpperCase();
  return `${setLabel} - ${titleizeSymbol(id)}`;
};

const hashSymbol = (value: string) => {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) | 0;
  }
  return Math.abs(hash);
};

const resolveSymbolColor = (id: string, set: MarkerSymbolSet) => {
  if (id in EXPLICIT_SYMBOL_COLORS) {
    return EXPLICIT_SYMBOL_COLORS[id];
  }
  const palette = set === "napsg" ? NAPSG_COLORS : MDI_COLORS;
  const index = hashSymbol(id) % palette.length;
  return palette[index];
};

const normalizeMdiName = (value: string) =>
  value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9-]+/g, "-")
    .replace(/^-+|-+$/g, "");

const buildSymbolFromEntry = (entry: MarkerSymbolEntry): MarkerSymbol | null => {
  const id = entry.id?.trim().toLowerCase();
  if (!id) {
    return null;
  }
  const set = normalizeMarkerSymbolSet(entry.set) ?? "mdi";
  const fallback = FALLBACK_SYMBOL_MAP.get(id);
  if (fallback) {
    return { ...fallback, set };
  }
  const description = typeof entry.description === "string" ? entry.description.trim() : "";
  const mdi = typeof entry.mdi === "string" ? normalizeMdiName(entry.mdi) : undefined;
  return {
    id,
    label: description || symbolLabel(id, set),
    set,
    color: resolveSymbolColor(id, set),
    mdi: mdi || (set === "mdi" ? id : undefined)
  };
};

export const markerSymbols = ref<MarkerSymbol[]>([...FALLBACK_SYMBOLS]);

const markerSymbolKeyMap = computed(
  () =>
    new Map(
      markerSymbols.value.map((symbol) => [
        buildMarkerSymbolKey(symbol.set, symbol.id),
        symbol
      ])
    )
);
const markerSymbolIdMap = computed(() => {
  const map = new Map<string, MarkerSymbol>();
  markerSymbols.value.forEach((symbol) => {
    if (!map.has(symbol.id)) {
      map.set(symbol.id, symbol);
    }
  });
  return map;
});

export const buildMarkerSymbols = (entries: MarkerSymbolEntry[]): MarkerSymbol[] => {
  const symbols = entries
    .map(buildSymbolFromEntry)
    .filter((symbol): symbol is MarkerSymbol => symbol !== null);
  return symbols.length ? symbols : [...FALLBACK_SYMBOLS];
};

export const setMarkerSymbols = (symbols: MarkerSymbol[]) => {
  markerSymbols.value = symbols.length ? symbols : [...FALLBACK_SYMBOLS];
};

export const getMarkerSymbol = (id: string, set?: string) => {
  const normalizedSet = normalizeMarkerSymbolSet(set);
  if (normalizedSet) {
    const keyed = markerSymbolKeyMap.value.get(buildMarkerSymbolKey(normalizedSet, id));
    if (keyed) {
      return keyed;
    }
  }
  return markerSymbolIdMap.value.get(id) ?? FALLBACK_SYMBOL_MAP.get(id);
};

export const getMarkerSymbolByKey = (key: string) => {
  const parsed = parseMarkerSymbolKey(key);
  return getMarkerSymbol(parsed.id, parsed.set);
};

export const resolveMarkerSymbolKey = (id: string, set?: string) => {
  const normalizedSet = normalizeMarkerSymbolSet(set);
  const symbol = getMarkerSymbol(id, normalizedSet);
  if (symbol) {
    return buildMarkerSymbolKey(symbol.set, symbol.id);
  }
  if (normalizedSet) {
    return buildMarkerSymbolKey(normalizedSet, id);
  }
  return buildMarkerSymbolKey("mdi", id);
};

export const defaultMarkerName = (category: string) => {
  const seed = Math.random().toString(16).slice(2, 8);
  const trimmed = category.trim() || "marker";
  return `${trimmed}+${seed}`;
};
