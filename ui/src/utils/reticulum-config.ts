export type KeyValueItem = {
  key: string;
  value: string;
};

export type ReticulumInterfaceEnableKey = "enabled" | "interface_enabled";

export type ReticulumInterfaceConfig = {
  id: string;
  name: string;
  type: string;
  enabled: boolean;
  enableKey: ReticulumInterfaceEnableKey;
  settings: KeyValueItem[];
};

export type ReticulumConfigState = {
  sections: Record<string, KeyValueItem[]>;
  sectionOrder: string[];
  interfaces: ReticulumInterfaceConfig[];
};

const TRUE_VALUES = new Set(["1", "true", "yes", "on", "y"]);
const FALSE_VALUES = new Set(["0", "false", "no", "off", "n"]);
const LIST_SEPARATOR_PATTERN = /[,;\r\n]+/;

let interfaceIdCounter = 0;

export const createInterfaceId = () => {
  interfaceIdCounter += 1;
  return `iface-${Date.now()}-${interfaceIdCounter}`;
};

export const createEmptyReticulumConfig = (): ReticulumConfigState => ({
  sections: {},
  sectionOrder: [],
  interfaces: [],
});

const normalizeSectionName = (name: string) => name.trim().toLowerCase();

export const parseBool = (value: string | undefined, defaultValue: boolean) => {
  if (!value) {
    return defaultValue;
  }
  const normalized = value.trim().toLowerCase();
  if (TRUE_VALUES.has(normalized)) {
    return true;
  }
  if (FALSE_VALUES.has(normalized)) {
    return false;
  }
  return defaultValue;
};

const toBoolValue = (value: boolean) => (value ? "yes" : "no");

const pushSection = (state: ReticulumConfigState, name: string) => {
  if (!state.sections[name]) {
    state.sections[name] = [];
  }
  if (!state.sectionOrder.includes(name)) {
    state.sectionOrder.push(name);
  }
};

const addKeyValue = (entries: KeyValueItem[], key: string, value: string) => {
  if (!key) {
    return;
  }
  entries.push({ key, value });
};

export const findEntryIndex = (entries: KeyValueItem[], key: string) =>
  entries.findIndex((entry) => entry.key.trim().toLowerCase() === key.trim().toLowerCase());

export const getEntryValue = (entries: KeyValueItem[], key: string) => {
  const index = findEntryIndex(entries, key);
  return index >= 0 ? entries[index].value : undefined;
};

export const setEntryValue = (entries: KeyValueItem[], key: string, value: string) => {
  const index = findEntryIndex(entries, key);
  if (index >= 0) {
    entries[index].value = value;
    return;
  }
  entries.push({ key, value });
};

export const removeEntry = (entries: KeyValueItem[], key: string) => {
  const index = findEntryIndex(entries, key);
  if (index >= 0) {
    entries.splice(index, 1);
  }
};

export const parseConfigList = (value: string | undefined): string[] => {
  if (!value) {
    return [];
  }
  return value
    .split(LIST_SEPARATOR_PATTERN)
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
};

export const serializeConfigList = (items: string[]): string =>
  items
    .map((item) => item.trim())
    .filter((item) => item.length > 0)
    .join(", ");

export const getEntryList = (entries: KeyValueItem[], key: string): string[] =>
  parseConfigList(getEntryValue(entries, key));

export const setEntryList = (entries: KeyValueItem[], key: string, items: string[]) => {
  const value = serializeConfigList(items);
  if (!value) {
    removeEntry(entries, key);
    return;
  }
  setEntryValue(entries, key, value);
};

export const parseReticulumConfig = (text: string): ReticulumConfigState => {
  const state = createEmptyReticulumConfig();
  if (!text) {
    return state;
  }

  const lines = text.split(/\r?\n/);
  let currentSection: string | null = null;
  let inInterfaces = false;
  let currentInterface: ReticulumInterfaceConfig | null = null;

  for (const rawLine of lines) {
    const trimmed = rawLine.trim();
    if (!trimmed || trimmed.startsWith("#") || trimmed.startsWith(";")) {
      continue;
    }

    const interfaceMatch = trimmed.match(/^\[\[(.+)\]\]$/);
    if (interfaceMatch && inInterfaces) {
      const name = interfaceMatch[1].trim();
      currentInterface = {
        id: createInterfaceId(),
        name,
        type: "",
        enabled: true,
        enableKey: "enabled",
        settings: [],
      };
      state.interfaces.push(currentInterface);
      continue;
    }

    const sectionMatch = trimmed.match(/^\[(.+)\]$/);
    if (sectionMatch) {
      const name = normalizeSectionName(sectionMatch[1]);
      currentSection = name;
      inInterfaces = name === "interfaces";
      currentInterface = null;
      pushSection(state, name);
      continue;
    }

    const equalsIndex = trimmed.indexOf("=");
    if (equalsIndex < 0) {
      continue;
    }
    const key = trimmed.slice(0, equalsIndex).trim();
    const value = trimmed.slice(equalsIndex + 1).trim();
    if (!key) {
      continue;
    }

    if (inInterfaces && currentInterface) {
      const lowerKey = key.toLowerCase();
      if (lowerKey === "type") {
        currentInterface.type = value;
      } else if (lowerKey === "interface_enabled" || lowerKey === "enabled") {
        currentInterface.enabled = parseBool(value, true);
        currentInterface.enableKey = lowerKey as ReticulumInterfaceEnableKey;
      } else {
        addKeyValue(currentInterface.settings, key, value);
      }
    } else if (currentSection) {
      addKeyValue(state.sections[currentSection], key, value);
    }
  }

  return state;
};

const serializeEntries = (entries: KeyValueItem[]) =>
  entries
    .filter((entry) => entry.key.trim().length > 0)
    .map((entry) => `${entry.key} = ${entry.value}`.trimEnd());

export const serializeReticulumConfig = (state: ReticulumConfigState): string => {
  const lines: string[] = [];
  const order = [...state.sectionOrder];

  const ensureOrder = (name: string) => {
    if (state.sections[name] && !order.includes(name)) {
      order.push(name);
    }
  };

  ensureOrder("reticulum");
  ensureOrder("logging");
  ensureOrder("interfaces");

  if (!order.length) {
    order.push("reticulum", "logging", "interfaces");
  }

  const appendBlank = () => {
    if (lines.length && lines[lines.length - 1] !== "") {
      lines.push("");
    }
  };

  for (const section of order) {
    if (section === "interfaces") {
      lines.push("[interfaces]");
      const globalEntries = state.sections[section] ?? [];
      lines.push(...serializeEntries(globalEntries));
      if (globalEntries.length || state.interfaces.length) {
        lines.push("");
      }
      state.interfaces.forEach((iface, index) => {
        const name = iface.name.trim() || `Interface ${index + 1}`;
        lines.push(`[[${name}]]`);
        if (iface.type.trim()) {
          lines.push(`type = ${iface.type}`.trimEnd());
        }
        const enableKey = iface.enableKey || "enabled";
        lines.push(`${enableKey} = ${toBoolValue(iface.enabled)}`);
        lines.push(...serializeEntries(iface.settings));
        lines.push("");
      });
      if (lines.length && lines[lines.length - 1] === "") {
        lines.pop();
      }
      appendBlank();
      continue;
    }

    const entries = state.sections[section] ?? [];
    if (!entries.length && section !== "reticulum" && section !== "logging") {
      continue;
    }
    lines.push(`[${section}]`);
    lines.push(...serializeEntries(entries));
    appendBlank();
  }

  if (lines.length && lines[lines.length - 1] === "") {
    lines.pop();
  }

  return `${lines.join("\n")}\n`;
};

const valueToConfigString = (value: unknown): string => {
  if (value === null || value === undefined) {
    return "";
  }
  if (typeof value === "boolean") {
    return value ? "yes" : "no";
  }
  if (typeof value === "number") {
    return Number.isFinite(value) ? String(value) : "";
  }
  if (typeof value === "string") {
    return value;
  }
  if (Array.isArray(value)) {
    return serializeConfigList(value.map((item) => valueToConfigString(item)));
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
};

export const parseReticulumInterfaceConfigEntry = (
  entry: string | Record<string, unknown>,
  fallbackName = "Discovered Interface"
): ReticulumInterfaceConfig | null => {
  if (typeof entry === "string") {
    const trimmed = entry.trim();
    if (!trimmed) {
      return null;
    }
    const snippet = trimmed.includes("[interfaces]")
      ? trimmed
      : trimmed.startsWith("[[")
        ? `[interfaces]\n${trimmed}\n`
        : `[interfaces]\n[[${fallbackName}]]\n${trimmed}\n`;
    const parsed = parseReticulumConfig(snippet);
    return parsed.interfaces[0] ?? null;
  }

  const nameRaw = valueToConfigString(entry.name);
  const typeRaw = valueToConfigString(entry.type);
  const enabledRaw =
    valueToConfigString(entry.interface_enabled) || valueToConfigString(entry.enabled);
  const hasEnabled = entry.interface_enabled !== undefined || entry.enabled !== undefined;
  const enableKey: ReticulumInterfaceEnableKey =
    entry.interface_enabled !== undefined ? "interface_enabled" : "enabled";

  const settings: KeyValueItem[] = [];
  Object.entries(entry).forEach(([key, value]) => {
    const normalized = key.trim().toLowerCase();
    if (!normalized || normalized === "name" || normalized === "type") {
      return;
    }
    if (normalized === "enabled" || normalized === "interface_enabled") {
      return;
    }
    settings.push({ key, value: valueToConfigString(value) });
  });

  return {
    id: createInterfaceId(),
    name: nameRaw.trim() || fallbackName,
    type: typeRaw.trim(),
    enabled: parseBool(enabledRaw, true),
    enableKey: hasEnabled ? enableKey : "enabled",
    settings,
  };
};
