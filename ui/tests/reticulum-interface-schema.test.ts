import { describe, expect, it } from "vitest";
import {
  getVisibleTypedFieldsForInterface,
} from "../src/utils/reticulum-interface-schema";

describe("reticulum interface schema visibility", () => {
  it("shows only TCP client core fields", () => {
    const fields = getVisibleTypedFieldsForInterface("TCPClientInterface", {
      capabilities: null,
      discoveryEnabled: false,
    });
    const keys = new Set(fields.map((field) => field.key));

    expect(keys.has("target_host")).toBe(true);
    expect(keys.has("target_port")).toBe(true);
    expect(keys.has("fixed_mtu")).toBe(false);
    expect(keys.has("mode")).toBe(false);
    expect(keys.has("passphrase")).toBe(false);
    expect(keys.has("listen_ip")).toBe(false);
    expect(keys.has("discovery_name")).toBe(false);
  });

  it("shows only core TCP server fields", () => {
    const fields = getVisibleTypedFieldsForInterface("TCPServerInterface", {
      capabilities: {
        runtime_active: true,
        os: "linux",
        identity_hash_hex_length: 20,
        supported_interface_types: ["TCPServerInterface"],
        unsupported_interface_types: [],
        discoverable_interface_types: ["TCPServerInterface"],
        autoconnect_interface_types: [],
        rns_version: "1.1.3",
      },
      discoveryEnabled: false,
    });
    const keys = new Set(fields.map((field) => field.key));
    expect(keys).toEqual(new Set(["listen_ip", "listen_port"]));
  });

  it("shows required RNode radio parameters", () => {
    const fields = getVisibleTypedFieldsForInterface("RNodeInterface", {
      capabilities: {
        runtime_active: true,
        os: "linux",
        identity_hash_hex_length: 20,
        supported_interface_types: ["RNodeInterface"],
        unsupported_interface_types: [],
        discoverable_interface_types: [],
        autoconnect_interface_types: [],
        rns_version: "1.1.3",
      },
      discoveryEnabled: false,
    });
    const keys = new Set(fields.map((field) => field.key));
    expect(keys).toEqual(
      new Set(["port", "frequency", "bandwidth", "txpower", "spreadingfactor", "codingrate"])
    );
  });
});
