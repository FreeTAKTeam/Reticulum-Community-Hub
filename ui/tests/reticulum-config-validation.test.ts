import { describe, expect, it } from "vitest";
import {
  parseConfigList,
  parseReticulumConfig,
  serializeReticulumConfig,
} from "../src/utils/reticulum-config";
import { validateReticulumConfigState } from "../src/utils/reticulum-config-validation";

describe("reticulum config parsing and validation", () => {
  it("parses both enabled key styles and preserves original style on serialize", () => {
    const source =
      "[interfaces]\n" +
      "[[alpha]]\n" +
      "type = TCPClientInterface\n" +
      "enabled = yes\n" +
      "target_host = 10.0.0.8\n" +
      "target_port = 4242\n" +
      "\n" +
      "[[bravo]]\n" +
      "type = UDPInterface\n" +
      "interface_enabled = no\n" +
      "listen_ip = 0.0.0.0\n" +
      "listen_port = 4242\n";

    const parsed = parseReticulumConfig(source);

    expect(parsed.interfaces).toHaveLength(2);
    expect(parsed.interfaces[0].enableKey).toBe("enabled");
    expect(parsed.interfaces[1].enableKey).toBe("interface_enabled");

    const serialized = serializeReticulumConfig(parsed);
    expect(serialized).toContain("enabled = yes");
    expect(serialized).toContain("interface_enabled = no");
  });

  it("parses list fields from comma/newline/semicolon separators", () => {
    const values = parseConfigList("aa11, bb22\ncc33; dd44");
    expect(values).toEqual(["aa11", "bb22", "cc33", "dd44"]);
  });

  it("defaults interface enable key style to enabled when not explicitly present", () => {
    const source =
      "[interfaces]\n" +
      "[[alpha]]\n" +
      "type = TCPClientInterface\n" +
      "target_host = 127.0.0.1\n" +
      "target_port = 4242\n";

    const parsed = parseReticulumConfig(source);
    expect(parsed.interfaces[0].enableKey).toBe("enabled");

    const serialized = serializeReticulumConfig(parsed);
    expect(serialized).toContain("enabled = yes");
    expect(serialized).not.toContain("interface_enabled =");
  });

  it("blocks hard invalid config values and emits warnings for risky discovery combinations", () => {
    const source =
      "[reticulum]\n" +
      "discover_interfaces = no\n" +
      "interface_discovery_sources = zz11\n" +
      "\n" +
      "[interfaces]\n" +
      "[[alpha]]\n" +
      "type = TCPClientInterface\n" +
      "interface_enabled = yes\n" +
      "discoverable = yes\n" +
      "interface_mode = roaming\n" +
      "target_port = 99999\n";

    const parsed = parseReticulumConfig(source);
    const result = validateReticulumConfigState(parsed);

    expect(result.valid).toBe(false);
    expect(result.errors.some((issue) => issue.path.includes("interface_discovery_sources"))).toBe(true);
    expect(result.errors.some((issue) => issue.path.includes("target_host"))).toBe(true);
    expect(result.errors.some((issue) => issue.path.includes("target_port"))).toBe(true);
    expect(result.warnings.some((issue) => issue.path.includes("discover_interfaces"))).toBe(true);
    expect(result.warnings.some((issue) => issue.path.includes("discoverable"))).toBe(true);
  });

  it("allows text-based serial port values", () => {
    const source =
      "[interfaces]\n" +
      "[[serial]]\n" +
      "type = SerialInterface\n" +
      "interface_enabled = yes\n" +
      "port = COM4\n" +
      "speed = 115200\n";

    const parsed = parseReticulumConfig(source);
    const result = validateReticulumConfigState(parsed);

    expect(result.errors.some((issue) => issue.path.endsWith(".port"))).toBe(false);
  });
});
