import type { ReticulumInterfaceCapabilities } from "../api/types";

export type ReticulumInterfaceType =
  | "AutoInterface"
  | "BackboneInterface"
  | "TCPServerInterface"
  | "TCPClientInterface"
  | "UDPInterface"
  | "I2PInterface"
  | "SerialInterface"
  | "KISSInterface"
  | "AX25KISSInterface"
  | "PipeInterface"
  | "RNodeInterface"
  | "RNodeMultiInterface"
  | "RNodeIPInterface";

export type ReticulumFieldKind = "text" | "number" | "boolean" | "select" | "list";

export type ReticulumFieldOption = {
  label: string;
  value: string;
};

export type ReticulumFieldDefinition = {
  key: string;
  label: string;
  kind: ReticulumFieldKind;
  description?: string;
  placeholder?: string;
  required?: boolean;
  min?: number;
  max?: number;
  step?: number;
  options?: ReticulumFieldOption[];
  aliases?: string[];
};

export type ReticulumTypeOption = {
  label: string;
  value: ReticulumInterfaceType;
};

export type ReticulumTypeGroup = {
  label: string;
  options: ReticulumTypeOption[];
};

const MODE_OPTIONS: ReticulumFieldOption[] = [
  { label: "Full", value: "full" },
  { label: "Gateway", value: "gateway" },
  { label: "Gateway (gw)", value: "gw" },
  { label: "Access Point", value: "access_point" },
  { label: "Access Point (ap)", value: "ap" },
  { label: "Roaming", value: "roaming" },
  { label: "Boundary", value: "boundary" },
];

const DISCOVERY_MODULATION_OPTIONS: ReticulumFieldOption[] = [
  { label: "LoRa", value: "lora" },
  { label: "FSK", value: "fsk" },
  { label: "OFDM", value: "ofdm" },
];

const PARITY_OPTIONS: ReticulumFieldOption[] = [
  { label: "None", value: "none" },
  { label: "Even", value: "even" },
  { label: "Odd", value: "odd" },
  { label: "N", value: "N" },
  { label: "E", value: "E" },
  { label: "O", value: "O" },
];

const STOP_BITS_OPTIONS: ReticulumFieldOption[] = [
  { label: "1", value: "1" },
  { label: "1.5", value: "1.5" },
  { label: "2", value: "2" },
];

const DATA_BITS_OPTIONS: ReticulumFieldOption[] = [
  { label: "7", value: "7" },
  { label: "8", value: "8" },
];

const BOOL_TEXT: ReticulumFieldOption[] = [
  { label: "Yes", value: "yes" },
  { label: "No", value: "no" },
];

const AUTO_DISCOVERY_SCOPE_OPTIONS: ReticulumFieldOption[] = [
  { label: "Link", value: "link" },
  { label: "Admin", value: "admin" },
  { label: "Site", value: "site" },
  { label: "Organisation", value: "organisation" },
  { label: "Global", value: "global" },
];

const MULTICAST_ADDRESS_TYPE_OPTIONS: ReticulumFieldOption[] = [
  { label: "Temporary", value: "temporary" },
  { label: "Permanent", value: "permanent" },
];

export const ALL_RETICULUM_INTERFACE_TYPES: ReticulumInterfaceType[] = [
  "AutoInterface",
  "BackboneInterface",
  "TCPServerInterface",
  "TCPClientInterface",
  "UDPInterface",
  "I2PInterface",
  "SerialInterface",
  "KISSInterface",
  "AX25KISSInterface",
  "PipeInterface",
  "RNodeInterface",
  "RNodeMultiInterface",
  "RNodeIPInterface",
];

export const DEFAULT_INTERFACE_TYPE: ReticulumInterfaceType = "TCPClientInterface";

export const INTERFACE_TYPE_GROUPS: ReticulumTypeGroup[] = [
  {
    label: "Automatic",
    options: [{ label: "Auto Interface", value: "AutoInterface" }],
  },
  {
    label: "IP Networks",
    options: [
      { label: "Backbone Interface", value: "BackboneInterface" },
      { label: "TCP Server Interface", value: "TCPServerInterface" },
      { label: "TCP Client Interface", value: "TCPClientInterface" },
      { label: "UDP Interface", value: "UDPInterface" },
      { label: "I2P Interface", value: "I2PInterface" },
    ],
  },
  {
    label: "Hardware",
    options: [
      { label: "Serial Interface", value: "SerialInterface" },
      { label: "KISS Interface", value: "KISSInterface" },
      { label: "AX.25 KISS Interface", value: "AX25KISSInterface" },
      { label: "RNode Interface", value: "RNodeInterface" },
      { label: "RNode Multi Interface", value: "RNodeMultiInterface" },
      { label: "RNode IP Interface", value: "RNodeIPInterface" },
    ],
  },
  {
    label: "Pipelines",
    options: [{ label: "Pipe Interface", value: "PipeInterface" }],
  },
];

export const RETICULUM_GLOBAL_DISCOVERY_FIELDS: ReticulumFieldDefinition[] = [
  {
    key: "discover_interfaces",
    label: "Discover interfaces",
    kind: "boolean",
    description: "Enable Reticulum announce-and-listen discovery globally.",
  },
  {
    key: "required_discovery_value",
    label: "Required discovery value",
    kind: "number",
    min: 0,
    max: 64,
    step: 1,
    description: "Minimum stamp value required for accepted discovery announces.",
  },
  {
    key: "autoconnect_discovered_interfaces",
    label: "Auto-connect limit",
    kind: "number",
    min: 0,
    step: 1,
    description: "Maximum number of discovered interfaces Reticulum may auto-connect.",
  },
  {
    key: "interface_discovery_sources",
    label: "Discovery source identities",
    kind: "list",
    placeholder: "Comma-separated identity hashes",
    description: "Optional allow-list of identity hashes trusted as discovery sources.",
  },
];

export const RETICULUM_INTERFACE_COMMON_FIELDS: ReticulumFieldDefinition[] = [
  {
    key: "mode",
    aliases: ["interface_mode"],
    label: "Mode",
    kind: "select",
    options: MODE_OPTIONS,
  },
  { key: "outgoing", label: "Outgoing", kind: "boolean" },
  { key: "bitrate", label: "Bitrate", kind: "number", min: 1, step: 1 },
  { key: "announce_cap", label: "Announce cap", kind: "number", min: 0, step: 1 },
  { key: "ifac_size", label: "IFAC size", kind: "number", min: 1, step: 1 },
  { key: "network_name", label: "Network name", kind: "text" },
  { key: "passphrase", aliases: ["pass_phrase"], label: "Passphrase", kind: "text" },
  { key: "ingress_control", label: "Ingress control", kind: "boolean" },
  { key: "announce_rate_target", label: "Announce target", kind: "number", min: 0, step: 1 },
  { key: "announce_rate_grace", label: "Announce grace", kind: "number", min: 0, step: 1 },
  { key: "announce_rate_penalty", label: "Announce penalty", kind: "number", min: 0, step: 1 },
  { key: "bootstrap_only", label: "Bootstrap only", kind: "boolean" },
  { key: "ignore_config_warnings", label: "Ignore warnings", kind: "boolean" },
];

export const RETICULUM_INTERFACE_DISCOVERY_FIELDS: ReticulumFieldDefinition[] = [
  { key: "discoverable", label: "Discoverable", kind: "boolean" },
  { key: "discovery_name", label: "Discovery name", kind: "text" },
  {
    key: "announce_interval",
    label: "Announce interval (s)",
    kind: "number",
    min: 5,
    step: 1,
  },
  {
    key: "discovery_stamp_value",
    label: "Discovery stamp value",
    kind: "number",
    min: 0,
    max: 64,
    step: 1,
  },
  { key: "discovery_encrypt", label: "Encrypt discovery payload", kind: "boolean" },
  { key: "reachable_on", label: "Reachable on host", kind: "text" },
  { key: "publish_ifac", label: "Publish IFAC credentials", kind: "boolean" },
  { key: "latitude", label: "Latitude", kind: "number", min: -90, max: 90, step: 0.000001 },
  { key: "longitude", label: "Longitude", kind: "number", min: -180, max: 180, step: 0.000001 },
  { key: "height", label: "Height", kind: "number", step: 0.1 },
  { key: "discovery_frequency", label: "Discovery frequency", kind: "number", min: 0, step: 1 },
  { key: "discovery_bandwidth", label: "Discovery bandwidth", kind: "number", min: 0, step: 1 },
  {
    key: "discovery_modulation",
    label: "Discovery modulation",
    kind: "select",
    options: DISCOVERY_MODULATION_OPTIONS,
  },
];

const TYPE_FIELD_DEFINITIONS: Record<ReticulumInterfaceType, ReticulumFieldDefinition[]> = {
  AutoInterface: [
    { key: "group_id", label: "Group ID", kind: "text" },
    {
      key: "multicast_address_type",
      label: "Multicast address type",
      kind: "select",
      options: MULTICAST_ADDRESS_TYPE_OPTIONS,
    },
    {
      key: "discovery_scope",
      label: "Discovery scope",
      kind: "select",
      options: AUTO_DISCOVERY_SCOPE_OPTIONS,
    },
    { key: "discovery_port", label: "Discovery port", kind: "number", min: 1, max: 65535, step: 1 },
    { key: "data_port", label: "Data port", kind: "number", min: 1, max: 65535, step: 1 },
    { key: "devices", label: "Devices", kind: "list" },
    { key: "ignored_devices", label: "Ignored devices", kind: "list" },
  ],
  BackboneInterface: [
    { key: "listen_on", aliases: ["listen_ip"], label: "Listen on host", kind: "text" },
    { key: "port", aliases: ["listen_port"], label: "Port", kind: "number", min: 1, max: 65535, step: 1 },
    { key: "target_host", aliases: ["remote"], label: "Target host", kind: "text" },
    { key: "target_port", label: "Target port", kind: "number", min: 1, max: 65535, step: 1 },
    { key: "prefer_ipv6", label: "Prefer IPv6", kind: "boolean" },
    { key: "device", label: "Device", kind: "text" },
  ],
  TCPServerInterface: [
    { key: "listen_ip", label: "Listen IP", kind: "text" },
    { key: "listen_port", aliases: ["port"], label: "Listen port", kind: "number", min: 1, max: 65535, step: 1 },
    { key: "prefer_ipv6", label: "Prefer IPv6", kind: "boolean" },
    { key: "device", label: "Device", kind: "text" },
    { key: "i2p_tunneled", label: "I2P tunneled", kind: "boolean" },
  ],
  TCPClientInterface: [
    { key: "target_host", label: "Target host", kind: "text" },
    { key: "target_port", label: "Target port", kind: "number", min: 1, max: 65535, step: 1 },
    { key: "fixed_mtu", label: "Fixed MTU", kind: "number", min: 1, step: 1 },
    { key: "kiss_framing", label: "KISS framing", kind: "boolean" },
    { key: "i2p_tunneled", label: "I2P tunneled", kind: "boolean" },
  ],
  UDPInterface: [
    { key: "listen_ip", label: "Listen IP", kind: "text" },
    { key: "listen_port", aliases: ["port"], label: "Listen port", kind: "number", min: 1, max: 65535, step: 1 },
    { key: "forward_ip", label: "Forward IP", kind: "text" },
    { key: "forward_port", label: "Forward port", kind: "number", min: 1, max: 65535, step: 1 },
    { key: "device", label: "Device", kind: "text" },
  ],
  I2PInterface: [
    { key: "peers", label: "Peers", kind: "list" },
    { key: "connectable", label: "Connectable", kind: "boolean" },
  ],
  SerialInterface: [
    { key: "port", label: "Port", kind: "text" },
    { key: "speed", label: "Speed", kind: "number", min: 1, step: 1 },
    { key: "databits", label: "Data bits", kind: "select", options: DATA_BITS_OPTIONS },
    { key: "parity", label: "Parity", kind: "select", options: PARITY_OPTIONS },
    { key: "stopbits", label: "Stop bits", kind: "select", options: STOP_BITS_OPTIONS },
  ],
  KISSInterface: [
    { key: "port", label: "Port", kind: "text" },
    { key: "speed", label: "Speed", kind: "number", min: 1, step: 1 },
    { key: "databits", label: "Data bits", kind: "select", options: DATA_BITS_OPTIONS },
    { key: "parity", label: "Parity", kind: "select", options: PARITY_OPTIONS },
    { key: "stopbits", label: "Stop bits", kind: "select", options: STOP_BITS_OPTIONS },
    { key: "preamble", label: "Preamble", kind: "number", min: 0, step: 1 },
    { key: "txtail", label: "TX tail", kind: "number", min: 0, step: 1 },
    { key: "persistence", label: "Persistence", kind: "number", min: 0, step: 1 },
    { key: "slottime", label: "Slot time", kind: "number", min: 0, step: 1 },
    { key: "flow_control", label: "Flow control", kind: "boolean" },
    { key: "id_interval", label: "ID interval", kind: "number", min: 0, step: 1 },
    { key: "id_callsign", label: "ID callsign", kind: "text" },
  ],
  AX25KISSInterface: [
    { key: "port", label: "Port", kind: "text" },
    { key: "speed", label: "Speed", kind: "number", min: 1, step: 1 },
    { key: "databits", label: "Data bits", kind: "select", options: DATA_BITS_OPTIONS },
    { key: "parity", label: "Parity", kind: "select", options: PARITY_OPTIONS },
    { key: "stopbits", label: "Stop bits", kind: "select", options: STOP_BITS_OPTIONS },
    { key: "preamble", label: "Preamble", kind: "number", min: 0, step: 1 },
    { key: "txtail", label: "TX tail", kind: "number", min: 0, step: 1 },
    { key: "persistence", label: "Persistence", kind: "number", min: 0, step: 1 },
    { key: "slottime", label: "Slot time", kind: "number", min: 0, step: 1 },
    { key: "flow_control", label: "Flow control", kind: "boolean" },
    { key: "id_interval", label: "ID interval", kind: "number", min: 0, step: 1 },
    { key: "id_callsign", label: "ID callsign", kind: "text" },
    { key: "callsign", label: "Callsign", kind: "text" },
    { key: "ssid", label: "SSID", kind: "number", min: 0, max: 15, step: 1 },
  ],
  PipeInterface: [
    { key: "command", label: "Command", kind: "text" },
    { key: "respawn_delay", aliases: ["respawn_interval"], label: "Respawn delay", kind: "number", min: 0, step: 0.1 },
  ],
  RNodeInterface: [
    { key: "port", label: "Port", kind: "text" },
    { key: "frequency", label: "Frequency", kind: "number", min: 0, step: 1 },
    { key: "bandwidth", label: "Bandwidth", kind: "number", min: 0, step: 1 },
    { key: "txpower", label: "TX power", kind: "number", step: 1 },
    { key: "spreadingfactor", label: "Spreading factor", kind: "number", min: 7, max: 12, step: 1 },
    { key: "codingrate", label: "Coding rate", kind: "number", min: 5, max: 8, step: 1 },
    { key: "flow_control", label: "Flow control", kind: "boolean" },
    { key: "id_interval", label: "ID interval", kind: "number", min: 0, step: 1 },
    { key: "id_callsign", label: "ID callsign", kind: "text" },
    { key: "airtime_limit_short", label: "Airtime short limit", kind: "number", min: 0, max: 100, step: 0.1 },
    { key: "airtime_limit_long", label: "Airtime long limit", kind: "number", min: 0, max: 100, step: 0.1 },
  ],
  RNodeMultiInterface: [
    { key: "port", label: "Port", kind: "text" },
    { key: "id_interval", label: "ID interval", kind: "number", min: 0, step: 1 },
    { key: "id_callsign", label: "ID callsign", kind: "text" },
    {
      key: "subinterfaces",
      label: "Subinterfaces",
      kind: "text",
      placeholder: "Use advanced settings for nested subinterface blocks",
      description: "RNodeMulti subinterface blocks remain editable from advanced settings.",
    },
  ],
  RNodeIPInterface: [
    { key: "target_host", label: "Target host", kind: "text" },
    { key: "target_port", label: "Target port", kind: "number", min: 1, max: 65535, step: 1 },
    { key: "password", label: "Password", kind: "text" },
  ],
};

export const YES_NO_OPTIONS = BOOL_TEXT;

const PRIMARY_TYPE_FIELD_KEYS: Partial<Record<ReticulumInterfaceType, string[]>> = {
  AutoInterface: ["group_id", "discovery_scope", "discovery_port", "data_port", "devices", "ignored_devices"],
  BackboneInterface: ["listen_on", "port", "target_host", "target_port"],
  TCPServerInterface: ["listen_ip", "listen_port"],
  TCPClientInterface: ["target_host", "target_port"],
  UDPInterface: ["listen_ip", "listen_port", "forward_ip", "forward_port"],
  I2PInterface: ["peers"],
  SerialInterface: ["port", "speed"],
  KISSInterface: ["port", "speed"],
  AX25KISSInterface: ["port", "callsign", "ssid"],
  PipeInterface: ["command"],
  RNodeInterface: ["port", "frequency", "bandwidth", "txpower", "spreadingfactor", "codingrate"],
  RNodeMultiInterface: ["port", "id_interval", "id_callsign"],
  RNodeIPInterface: ["target_host", "target_port"],
};

const dedupeFields = (fields: ReticulumFieldDefinition[]) => {
  const deduped = new Map<string, ReticulumFieldDefinition>();
  fields.forEach((field) => {
    deduped.set(field.key, field);
  });
  return Array.from(deduped.values());
};

export const getTypeSpecificFields = (interfaceType: string): ReticulumFieldDefinition[] => {
  if (!ALL_RETICULUM_INTERFACE_TYPES.includes(interfaceType as ReticulumInterfaceType)) {
    return [];
  }
  return TYPE_FIELD_DEFINITIONS[interfaceType as ReticulumInterfaceType] ?? [];
};

export const isInterfaceTypeDiscoverable = (
  interfaceType: string,
  capabilities?: ReticulumInterfaceCapabilities | null
) => {
  const runtimeTypes = capabilities?.discoverable_interface_types ?? [];
  return runtimeTypes.includes(interfaceType);
};

export const getVisibleTypedFieldsForInterface = (
  interfaceType: string,
  options?: {
    capabilities?: ReticulumInterfaceCapabilities | null;
    discoveryEnabled?: boolean;
  }
): ReticulumFieldDefinition[] => {
  void options;
  const allTypeFields = getTypeSpecificFields(interfaceType).filter((field) => field.key !== "subinterfaces");
  const primaryKeys = new Set(
    (PRIMARY_TYPE_FIELD_KEYS[interfaceType as ReticulumInterfaceType] ?? allTypeFields.map((field) => field.key)).map(
      (key) => key.toLowerCase()
    )
  );
  return dedupeFields(allTypeFields.filter((field) => primaryKeys.has(field.key.toLowerCase())));
};

export const getAllTypedFieldsForInterface = (interfaceType: string): ReticulumFieldDefinition[] => {
  const fields = [
    ...RETICULUM_INTERFACE_COMMON_FIELDS,
    ...RETICULUM_INTERFACE_DISCOVERY_FIELDS,
    ...getTypeSpecificFields(interfaceType),
  ];
  return dedupeFields(fields);
};

export const getSupportedTypeSet = (
  capabilities?: ReticulumInterfaceCapabilities | null
): Set<ReticulumInterfaceType> => {
  const supportedFromRuntime = new Set(
    (capabilities?.supported_interface_types ?? []).filter((type): type is ReticulumInterfaceType =>
      ALL_RETICULUM_INTERFACE_TYPES.includes(type as ReticulumInterfaceType)
    )
  );

  if (supportedFromRuntime.size > 0) {
    return supportedFromRuntime;
  }

  return new Set(
    ALL_RETICULUM_INTERFACE_TYPES.filter((type) => type !== "RNodeIPInterface")
  );
};

export const getCreatableInterfaceTypeGroups = (
  capabilities?: ReticulumInterfaceCapabilities | null
): ReticulumTypeGroup[] => {
  const supported = getSupportedTypeSet(capabilities);
  return INTERFACE_TYPE_GROUPS.map((group) => ({
    label: group.label,
    options: group.options.filter((option) => supported.has(option.value)),
  })).filter((group) => group.options.length > 0);
};

export const isInterfaceTypeCreatable = (
  interfaceType: string,
  capabilities?: ReticulumInterfaceCapabilities | null
) => {
  const groups = getCreatableInterfaceTypeGroups(capabilities);
  return groups.some((group) => group.options.some((option) => option.value === interfaceType));
};
