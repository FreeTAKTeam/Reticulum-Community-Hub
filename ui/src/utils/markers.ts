export type MarkerSymbolSet = "napsg" | "maki";

export type MarkerSymbol = {
  id: string;
  label: string;
  set: MarkerSymbolSet;
  color: string;
};

export const markerSymbols: MarkerSymbol[] = [
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

export const markerSymbolMap = new Map(markerSymbols.map((symbol) => [symbol.id, symbol]));

export const getMarkerSymbol = (id: string) => markerSymbolMap.get(id);

export const defaultMarkerName = (category: string) => {
  const seed = Math.random().toString(16).slice(2, 8);
  const trimmed = category.trim() || "marker";
  return `${trimmed}+${seed}`;
};
