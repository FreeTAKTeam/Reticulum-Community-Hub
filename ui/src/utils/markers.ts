import { computed } from "vue";
import { ref } from "vue";
import type { MarkerSymbolEntry } from "../api/types";

export type MarkerSymbolSet = "napsg" | "maki";

export type MarkerSymbol = {
  id: string;
  label: string;
  set: MarkerSymbolSet;
  color: string;
};

const NAPSG_COLORS = ["#F97316", "#FACC15", "#EF4444", "#60A5FA", "#FBBF24", "#34D399"];
const MAKI_COLORS = ["#38BDF8", "#A78BFA", "#F59E0B", "#F87171", "#22D3EE", "#94A3B8"];

const FALLBACK_SYMBOLS: MarkerSymbol[] = [
  { id: "fire", label: "NAPSG - Fire", set: "napsg", color: "#F97316" },
  { id: "hazmat", label: "NAPSG - Hazmat", set: "napsg", color: "#FACC15" },
  { id: "medical", label: "NAPSG - Medical", set: "napsg", color: "#EF4444" },
  { id: "police", label: "NAPSG - Police", set: "napsg", color: "#60A5FA" },
  { id: "search", label: "NAPSG - Search", set: "napsg", color: "#FBBF24" },
  { id: "shelter", label: "NAPSG - Shelter", set: "napsg", color: "#34D399" },
  { id: "marker", label: "Maki - Marker", set: "maki", color: "#38BDF8" },
  { id: "town-hall", label: "Maki - Town Hall", set: "maki", color: "#A78BFA" },
  { id: "dog-park", label: "Maki - Dog Park", set: "maki", color: "#F59E0B" },
  { id: "hospital", label: "Maki - Hospital", set: "maki", color: "#F87171" },
  { id: "bus", label: "Maki - Bus", set: "maki", color: "#22D3EE" },
  { id: "airfield", label: "Maki - Airfield", set: "maki", color: "#94A3B8" }
];

const FALLBACK_SYMBOL_MAP = new Map(
  FALLBACK_SYMBOLS.map((symbol) => [symbol.id, symbol])
);

export const normalizeMarkerSymbolSet = (value?: string): MarkerSymbolSet | undefined => {
  const normalized = value?.toLowerCase();
  if (normalized === "napsg" || normalized === "maki") {
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
    .split("-")
    .filter((segment) => segment)
    .map((segment) => segment[0]?.toUpperCase() + segment.slice(1))
    .join(" ");

const symbolLabel = (id: string, set: MarkerSymbolSet) => {
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
  const palette = set === "napsg" ? NAPSG_COLORS : MAKI_COLORS;
  const index = hashSymbol(id) % palette.length;
  return palette[index];
};

const buildSymbolFromEntry = (entry: MarkerSymbolEntry): MarkerSymbol | null => {
  const id = entry.id?.trim().toLowerCase();
  if (!id) {
    return null;
  }
  const set = normalizeMarkerSymbolSet(entry.set) ?? "maki";
  const fallback = FALLBACK_SYMBOL_MAP.get(id);
  if (fallback) {
    return { ...fallback, set };
  }
  return {
    id,
    label: symbolLabel(id, set),
    set,
    color: resolveSymbolColor(id, set)
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
  return buildMarkerSymbolKey("maki", id);
};

export const defaultMarkerName = (category: string) => {
  const seed = Math.random().toString(16).slice(2, 8);
  const trimmed = category.trim() || "marker";
  return `${trimmed}+${seed}`;
};
