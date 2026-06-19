export interface MecpDisplay {
  raw: string;
  severityLabel: string;
  severityStatus: string;
  categoryLabel: string;
  codeLabels: string[];
  extraLabels: string[];
  details: string;
  warnings: string[];
}

const readObject = (value: unknown): Record<string, unknown> | null =>
  value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;

const readString = (value: unknown): string => (typeof value === "string" ? value.trim() : "");

const readStringArray = (value: unknown): string[] =>
  Array.isArray(value)
    ? value.map((item) => readString(item)).filter((item) => item.length > 0)
    : [];

const readNumber = (value: unknown): number | null => {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return null;
  }
  return value;
};

const severityDisplay: Record<string, { label: string; status: string }> = {
  "0": { label: "Mayday", status: "red" },
  "1": { label: "Urgent", status: "yellow" },
  "2": { label: "Safety", status: "green" },
  "3": { label: "Routine", status: "blue" }
};

const categoryLabels: Record<string, string> = {
  M: "Medical",
  T: "Terrain / Infrastructure",
  W: "Weather / Environment",
  S: "Supplies",
  P: "Position / Movement",
  C: "Coordination",
  R: "Response",
  D: "Drill / Test",
  L: "Life / Leisure",
  X: "Threat / Security",
  H: "Have / Offer Resources",
  B: "Beacon"
};

const eventLabels: Record<string, string> = {
  C01: "Send rescue",
  C04: "Confirm received",
  C08: "Rendezvous at",
  D01: "This is a drill",
  D02: "This is a test",
  H01: "Have water available",
  H04: "Have power / charging",
  H08: "Have transport / vehicle",
  M01: "Injury",
  M06: "Severe bleeding",
  M14: "Persons located alive",
  P01: "Stranded / stuck",
  P02: "Evacuating toward",
  P03: "Sheltering in place",
  P05: "At GPS coordinates",
  R01: "Acknowledged",
  R02: "Help coming",
  R03: "ETA [minutes]",
  S01: "Need water",
  S02: "Need food",
  S03: "Need medication",
  S04: "Need battery / power",
  T01: "Road blocked",
  T02: "Bridge out",
  T06: "Power out",
  T16: "Vehicle accident",
  W01: "Storm approaching",
  W02: "Visibility zero",
  W05: "Air quality danger",
  X01: "Dangerous person / threat nearby",
  X02: "Area unsafe - avoid"
};

const isMecpCode = (value: string): boolean => /^[A-Z][0-9]{2}$/.test(value);

function normalizeMecpContentFallback(input: unknown): MecpDisplay | null {
  const raw = readString(input);
  if (!raw.startsWith("MECP/")) {
    return null;
  }

  const match = /^MECP\/([0-3])\/(.+)$/i.exec(raw);
  if (!match) {
    return null;
  }

  const severity = severityDisplay[match[1]];
  const tokens = match[2].trim().split(/\s+/).filter((token) => token.length > 0);
  const codes: string[] = [];
  let detailsStart = tokens.length;
  for (const [index, token] of tokens.entries()) {
    const code = token.toUpperCase();
    if (!isMecpCode(code)) {
      detailsStart = index;
      break;
    }
    codes.push(code);
  }
  if (!severity || !codes.length) {
    return null;
  }

  const details = tokens.slice(detailsStart).join(" ");
  const warnings: string[] = [];
  const codeLabels = codes.map((code) => {
    const label = eventLabels[code];
    if (!label) {
      warnings.push(`Unknown MECP event code "${code}".`);
      return code;
    }
    return `${code} ${label}`;
  });
  const category = codes[0]?.slice(0, 1) ?? "";

  return {
    raw,
    severityLabel: severity.label,
    severityStatus: severity.status,
    categoryLabel: categoryLabels[category] ?? "MECP",
    codeLabels,
    extraLabels: [],
    details,
    warnings
  };
}

export function normalizeMecpDisplay(input: unknown, fallbackContent?: unknown): MecpDisplay | null {
  const raw = readObject(input);
  if (!raw || raw.valid !== true) {
    return normalizeMecpContentFallback(fallbackContent);
  }

  const codeLabels = Array.isArray(raw.code_details)
    ? raw.code_details
        .map((item) => {
          const code = readObject(item);
          if (!code) {
            return "";
          }
          const value = readString(code.code);
          const label = readString(code.label);
          return label && label !== value ? `${value} ${label}` : value;
        })
        .filter((item) => item.length > 0)
    : [];

  const extras = readObject(raw.extras);
  const extraLabels: string[] = [];
  const pax = readNumber(extras?.pax);
  const eta = readNumber(extras?.eta_minutes);
  if (pax !== null) {
    extraLabels.push(`${pax} pax`);
  }
  if (eta !== null) {
    extraLabels.push(`ETA ${eta} min`);
  }
  extraLabels.push(...readStringArray(extras?.references));
  const coordinates = readObject(extras?.coordinates);
  const latitude = readNumber(coordinates?.latitude);
  const longitude = readNumber(coordinates?.longitude);
  if (latitude !== null && longitude !== null) {
    extraLabels.push(`${latitude},${longitude}`);
  }

  return {
    raw: readString(raw.raw),
    severityLabel: readString(raw.severity_label) || "Unknown",
    severityStatus: readString(raw.severity_status) || "unknown",
    categoryLabel: readString(raw.category_label) || "MECP",
    codeLabels,
    extraLabels,
    details: readString(raw.details),
    warnings: readStringArray(raw.warnings)
  };
}
