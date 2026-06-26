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
const BOOLEAN_VALUE_KEYS = new Set([
  "enabled",
  "interface_enabled",
  "discover_interfaces",
  "outgoing",
  "ingress_control",
  "bootstrap_only",
  "ignore_config_warnings",
  "discoverable",
  "discovery_encrypt",
  "publish_ifac",
  "prefer_ipv6",
  "i2p_tunneled",
  "kiss_framing",
  "connectable",
  "flow_control",
]);
const LIST_VALUE_KEYS = new Set([
  "interface_discovery_sources",
  "devices",
  "ignored_devices",
  "peers",
]);
const NUMBER_VALUE_KEYS = new Set([
  "required_discovery_value",
  "autoconnect_discovered_interfaces",
  "bitrate",
  "announce_cap",
  "ifac_size",
  "announce_rate_target",
  "announce_rate_grace",
  "announce_rate_penalty",
  "announce_interval",
  "discovery_stamp_value",
  "latitude",
  "longitude",
  "height",
  "discovery_frequency",
  "discovery_bandwidth",
  "discovery_port",
  "data_port",
  "listen_port",
  "target_port",
  "forward_port",
  "fixed_mtu",
  "speed",
  "preamble",
  "txtail",
  "persistence",
  "slottime",
  "id_interval",
  "ssid",
  "frequency",
  "bandwidth",
  "txpower",
  "spreadingfactor",
  "codingrate",
  "airtime_limit_short",
  "airtime_limit_long",
  "respawn_delay",
  "respawn_interval",
]);
const NUMERIC_PORT_INTERFACE_TYPES = new Set([
  "tcpclientinterface",
  "tcp_client",
  "tcpserverinterface",
  "tcp_server",
  "udpinterface",
  "udp",
  "backboneinterface",
  "backbone",
  "backboneclientinterface",
  "backbone_client",
  "localinterface",
  "local",
]);

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

const unquoteConfigValue = (value: string) => {
  const trimmed = value.trim();
  if (trimmed.length < 2) {
    return trimmed;
  }
  if (trimmed.startsWith('"') && trimmed.endsWith('"')) {
    try {
      const parsed = JSON.parse(trimmed);
      return typeof parsed === "string" ? parsed : trimmed;
    } catch {
      return trimmed.slice(1, -1);
    }
  }
  if (trimmed.startsWith("'") && trimmed.endsWith("'")) {
    return trimmed.slice(1, -1);
  }
  return trimmed;
};

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

const isTomlNumber = (value: string) => {
  const normalized = value.trim().replaceAll("_", "");
  if (!/^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$/.test(normalized)) {
    return false;
  }
  return Number.isFinite(Number(normalized));
};

const tomlString = (value: string) => JSON.stringify(value);

const usesNumericPort = (interfaceType: string | undefined) =>
  Boolean(interfaceType && NUMERIC_PORT_INTERFACE_TYPES.has(interfaceType.trim().toLowerCase()));

const toTomlValue = (key: string, value: string, interfaceType?: string) => {
  const normalizedKey = key.trim().toLowerCase();
  const normalizedValue = value.trim();
  const boolValue = parseBool(normalizedValue, false);

  if (
    BOOLEAN_VALUE_KEYS.has(normalizedKey) &&
    (TRUE_VALUES.has(normalizedValue.toLowerCase()) || FALSE_VALUES.has(normalizedValue.toLowerCase()))
  ) {
    return boolValue ? "true" : "false";
  }

  if (LIST_VALUE_KEYS.has(normalizedKey)) {
    const values = parseConfigList(normalizedValue);
    return `[${values.map(tomlString).join(", ")}]`;
  }

  if (
    (NUMBER_VALUE_KEYS.has(normalizedKey) || (normalizedKey === "port" && usesNumericPort(interfaceType))) &&
    isTomlNumber(normalizedValue)
  ) {
    return normalizedValue.replaceAll("_", "");
  }

  return tomlString(normalizedValue);
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

    const tomlInterfaceMatch = trimmed.match(/^\[\[interfaces\]\]$/i);
    if (tomlInterfaceMatch) {
      currentSection = "interfaces";
      inInterfaces = true;
      currentInterface = {
        id: createInterfaceId(),
        name: `Interface ${state.interfaces.length + 1}`,
        type: "",
        enabled: true,
        enableKey: "enabled",
        settings: [],
      };
      state.interfaces.push(currentInterface);
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
    const value = unquoteConfigValue(trimmed.slice(equalsIndex + 1));
    if (!key) {
      continue;
    }

    if (inInterfaces && currentInterface) {
      const lowerKey = key.toLowerCase();
      if (lowerKey === "type") {
        currentInterface.type = value;
      } else if (lowerKey === "name") {
        currentInterface.name = value || currentInterface.name;
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

const serializeEntries = (entries: KeyValueItem[], interfaceType?: string) =>
  entries
    .filter((entry) => entry.key.trim().length > 0)
    .map((entry) => `${entry.key} = ${toTomlValue(entry.key, entry.value, interfaceType)}`.trimEnd());

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
  if (!order.length) {
    order.push("reticulum", "logging");
  }

  const appendBlank = () => {
    if (lines.length && lines[lines.length - 1] !== "") {
      lines.push("");
    }
  };

  for (const section of order) {
    if (section === "interfaces") {
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

  if (state.interfaces.length) {
    appendBlank();
    state.interfaces.forEach((iface, index) => {
      const name = iface.name.trim() || `Interface ${index + 1}`;
      lines.push("[[interfaces]]");
      lines.push(`name = ${tomlString(name)}`);
      if (iface.type.trim()) {
        lines.push(`type = ${tomlString(iface.type.trim())}`);
      }
      const enableKey = iface.enableKey || "enabled";
      lines.push(`${enableKey} = ${iface.enabled ? "true" : "false"}`);
      lines.push(...serializeEntries(iface.settings, iface.type));
      lines.push("");
    });
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
