import type { ReticulumConfigState } from "./reticulum-config";
import type { ReticulumInterfaceConfig } from "./reticulum-config";
import { getEntryValue } from "./reticulum-config";
import { parseBool } from "./reticulum-config";
import { parseConfigList } from "./reticulum-config";
import {
  getAllTypedFieldsForInterface,
  RETICULUM_GLOBAL_DISCOVERY_FIELDS,
  type ReticulumFieldDefinition,
} from "./reticulum-interface-schema";

export type ReticulumValidationIssueLevel = "error" | "warning";

export type ReticulumValidationIssue = {
  level: ReticulumValidationIssueLevel;
  path: string;
  message: string;
};

export type ReticulumValidationResult = {
  valid: boolean;
  errors: ReticulumValidationIssue[];
  warnings: ReticulumValidationIssue[];
};

const HEX_RE = /^[0-9a-f]+$/i;
const HOST_RE = /^([a-z0-9-_.]+|\[[0-9a-f:]+\])$/i;
const IPV4_RE = /^(25[0-5]|2[0-4]\d|1?\d?\d)(\.(25[0-5]|2[0-4]\d|1?\d?\d)){3}$/;
const INTERFACE_NAME_MAX = 96;

const addIssue = (
  bucket: ReticulumValidationIssue[],
  level: ReticulumValidationIssueLevel,
  path: string,
  message: string
) => {
  bucket.push({ level, path, message });
};

const asNumber = (value: string | undefined): number | null => {
  if (value === undefined || value.trim() === "") {
    return null;
  }
  const parsed = Number(value.trim());
  if (!Number.isFinite(parsed)) {
    return null;
  }
  return parsed;
};

const validateHexIdentity = (value: string) => {
  const normalized = value.trim().toLowerCase();
  if (!normalized) {
    return false;
  }
  if (!HEX_RE.test(normalized)) {
    return false;
  }
  return normalized.length % 2 === 0;
};

const isLikelyHost = (value: string) => {
  const normalized = value.trim();
  if (!normalized) {
    return false;
  }
  if (normalized === "*" || normalized === "0.0.0.0" || normalized === "::") {
    return true;
  }
  return HOST_RE.test(normalized) || IPV4_RE.test(normalized);
};

const getSettingValue = (iface: ReticulumInterfaceConfig, field: ReticulumFieldDefinition) => {
  const aliases = [field.key, ...(field.aliases ?? [])];
  for (const alias of aliases) {
    const value = getEntryValue(iface.settings, alias);
    if (value !== undefined) {
      return value;
    }
  }
  return undefined;
};

const validateFieldValue = (
  field: ReticulumFieldDefinition,
  value: string | undefined,
  issues: ReticulumValidationIssue[],
  pathPrefix: string
) => {
  if (value === undefined || value.trim() === "") {
    if (field.required) {
      addIssue(issues, "error", `${pathPrefix}.${field.key}`, `${field.label} is required`);
    }
    return;
  }

  if (field.kind === "number") {
    const parsed = asNumber(value);
    if (parsed === null) {
      addIssue(issues, "error", `${pathPrefix}.${field.key}`, `${field.label} must be a number`);
      return;
    }
    if (field.min !== undefined && parsed < field.min) {
      addIssue(issues, "error", `${pathPrefix}.${field.key}`, `${field.label} must be >= ${field.min}`);
    }
    if (field.max !== undefined && parsed > field.max) {
      addIssue(issues, "error", `${pathPrefix}.${field.key}`, `${field.label} must be <= ${field.max}`);
    }
    if (field.step === 1 && !Number.isInteger(parsed)) {
      addIssue(issues, "error", `${pathPrefix}.${field.key}`, `${field.label} must be an integer`);
    }
    return;
  }

  if (field.kind === "boolean") {
    const normalized = value.trim().toLowerCase();
    if (!["yes", "no", "true", "false", "1", "0", "on", "off", "y", "n"].includes(normalized)) {
      addIssue(issues, "error", `${pathPrefix}.${field.key}`, `${field.label} must be yes/no`);
    }
    return;
  }

  if (field.kind === "select" && field.options && field.options.length > 0) {
    const allowed = new Set(field.options.map((option) => option.value));
    if (!allowed.has(value.trim())) {
      addIssue(
        issues,
        "error",
        `${pathPrefix}.${field.key}`,
        `${field.label} must be one of: ${field.options.map((option) => option.value).join(", ")}`
      );
    }
    return;
  }

  if (field.kind === "list") {
    const listValues = parseConfigList(value);
    if (!listValues.length && field.required) {
      addIssue(issues, "error", `${pathPrefix}.${field.key}`, `${field.label} must contain at least one value`);
    }
  }
};

const validateGlobalDiscovery = (state: ReticulumConfigState, issues: ReticulumValidationIssue[]) => {
  const reticulum = state.sections.reticulum ?? [];
  RETICULUM_GLOBAL_DISCOVERY_FIELDS.forEach((field) => {
    const value = getEntryValue(reticulum, field.key);
    validateFieldValue(field, value, issues, "reticulum");
  });

  const sources = parseConfigList(getEntryValue(reticulum, "interface_discovery_sources"));
  sources.forEach((source, index) => {
    if (!validateHexIdentity(source)) {
      addIssue(
        issues,
        "error",
        `reticulum.interface_discovery_sources[${index}]`,
        "Discovery source identity must be an even-length hex string"
      );
    }
  });
};

type RequiredFieldRule = {
  key: string;
  aliases?: string[];
};

const REQUIRED_FIELDS_BY_TYPE: Record<string, RequiredFieldRule[]> = {
  TCPClientInterface: [{ key: "target_host" }, { key: "target_port" }],
  TCPServerInterface: [{ key: "listen_port", aliases: ["port"] }],
  UDPInterface: [
    { key: "listen_ip", aliases: ["device"] },
    { key: "listen_port", aliases: ["port"] },
  ],
  SerialInterface: [{ key: "port" }],
  KISSInterface: [{ key: "port" }],
  AX25KISSInterface: [{ key: "port" }, { key: "callsign" }],
  PipeInterface: [{ key: "command" }],
  RNodeInterface: [{ key: "port" }],
  RNodeMultiInterface: [{ key: "port" }],
  RNodeIPInterface: [{ key: "target_host" }, { key: "target_port" }],
};

const hasAnySettingValue = (iface: ReticulumInterfaceConfig, keys: string[]) =>
  keys.some((key) => {
    const value = getEntryValue(iface.settings, key);
    return Boolean(value && value.trim());
  });

const hasRequiredValue = (iface: ReticulumInterfaceConfig, rule: RequiredFieldRule) =>
  hasAnySettingValue(iface, [rule.key, ...(rule.aliases ?? [])]);

const validateInterface = (
  iface: ReticulumInterfaceConfig,
  index: number,
  issues: ReticulumValidationIssue[]
) => {
  const pathPrefix = `interfaces[${index}]`;
  const name = iface.name.trim();
  if (!name) {
    addIssue(issues, "error", `${pathPrefix}.name`, "Interface name is required");
  } else if (name.length > INTERFACE_NAME_MAX) {
    addIssue(
      issues,
      "error",
      `${pathPrefix}.name`,
      `Interface name must be ${INTERFACE_NAME_MAX} characters or fewer`
    );
  }
  if (!iface.type.trim()) {
    addIssue(issues, "error", `${pathPrefix}.type`, "Interface type is required");
  }

  const typedFields = getAllTypedFieldsForInterface(iface.type);
  typedFields.forEach((field) => {
    const value = getSettingValue(iface, field);
    validateFieldValue(field, value, issues, pathPrefix);
  });

  (REQUIRED_FIELDS_BY_TYPE[iface.type] ?? []).forEach((rule) => {
    if (!hasRequiredValue(iface, rule)) {
      addIssue(
        issues,
        "error",
        `${pathPrefix}.${rule.key}`,
        `${rule.key} is required for ${iface.type}`
      );
    }
  });

  if (iface.type === "BackboneInterface") {
    const hasAddress = hasAnySettingValue(iface, ["listen_on", "listen_ip", "device", "target_host", "remote"]);
    const hasPort = hasAnySettingValue(iface, ["port", "listen_port", "target_port"]);
    if (!hasAddress) {
      addIssue(
        issues,
        "error",
        `${pathPrefix}.listen_on`,
        "BackboneInterface requires listen_on/listen_ip/device or target_host/remote"
      );
    }
    if (!hasPort) {
      addIssue(
        issues,
        "error",
        `${pathPrefix}.port`,
        "BackboneInterface requires port/listen_port or target_port"
      );
    }
  }

  iface.settings.forEach((entry) => {
    const key = entry.key.trim().toLowerCase();
    const value = entry.value.trim();
    if (!key || !value) {
      return;
    }
    if (
      key.endsWith("_host") ||
      key.endsWith("_ip") ||
      key === "reachable_on" ||
      key === "listen_ip" ||
      key === "listen_on" ||
      key === "remote"
    ) {
      if (!isLikelyHost(value)) {
        addIssue(issues, "error", `${pathPrefix}.${entry.key}`, `${entry.key} must be a valid host or IP`);
      }
    }
    const numericPlainPort =
      key === "port" &&
      ["BackboneInterface", "TCPServerInterface", "UDPInterface"].includes(iface.type);
    if (key.endsWith("_port") || numericPlainPort) {
      const port = asNumber(value);
      if (port === null || !Number.isInteger(port) || port < 1 || port > 65535) {
        addIssue(issues, "error", `${pathPrefix}.${entry.key}`, `${entry.key} must be an integer between 1 and 65535`);
      }
    }
  });
};

const validateWarnings = (
  state: ReticulumConfigState,
  issues: ReticulumValidationIssue[]
) => {
  const reticulum = state.sections.reticulum ?? [];
  const discoverInterfacesEnabled = parseBool(getEntryValue(reticulum, "discover_interfaces"), false);
  const autoconnectLimit = asNumber(getEntryValue(reticulum, "autoconnect_discovered_interfaces"));

  let discoverableCount = 0;

  state.interfaces.forEach((iface, index) => {
    const discoverable = parseBool(getEntryValue(iface.settings, "discoverable"), false);
    if (!discoverable) {
      return;
    }
    discoverableCount += 1;
    const modeValue =
      getEntryValue(iface.settings, "interface_mode") ??
      getEntryValue(iface.settings, "mode") ??
      "";
    if (modeValue && !["gateway", "access_point", "ap"].includes(modeValue.trim().toLowerCase())) {
      addIssue(
        issues,
        "warning",
        `interfaces[${index}].discoverable`,
        "Discoverable is usually paired with gateway/access_point mode"
      );
    }
  });

  if (!discoverInterfacesEnabled && discoverableCount > 0) {
    addIssue(
      issues,
      "warning",
      "reticulum.discover_interfaces",
      "Global discover_interfaces is disabled while one or more interfaces are discoverable"
    );
  }

  if (!discoverInterfacesEnabled && autoconnectLimit !== null && autoconnectLimit > 0) {
    addIssue(
      issues,
      "warning",
      "reticulum.autoconnect_discovered_interfaces",
      "Auto-connect is configured but global discovery is disabled"
    );
  }
};

export const validateReticulumConfigState = (state: ReticulumConfigState): ReticulumValidationResult => {
  const errors: ReticulumValidationIssue[] = [];
  const warnings: ReticulumValidationIssue[] = [];

  validateGlobalDiscovery(state, errors);
  state.interfaces.forEach((iface, index) => validateInterface(iface, index, errors));
  validateWarnings(state, warnings);

  return {
    valid: errors.length === 0,
    errors,
    warnings,
  };
};
