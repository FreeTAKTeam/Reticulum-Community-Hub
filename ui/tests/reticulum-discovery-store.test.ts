import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useReticulumDiscoveryStore } from "../src/stores/reticulum-discovery";

const capabilitiesPayload = {
  runtime_active: true,
  os: "windows",
  identity_hash_hex_length: 20,
  supported_interface_types: ["TCPClientInterface", "UDPInterface"],
  unsupported_interface_types: ["RNodeIPInterface"],
  discoverable_interface_types: ["UDPInterface"],
  autoconnect_interface_types: ["TCPClientInterface"],
  rns_version: "1.1.3",
} as const;

const discoveryPayload = {
  runtime_active: true,
  should_autoconnect: true,
  max_autoconnected_interfaces: 3,
  required_discovery_value: 14,
  interface_discovery_sources: [],
  discovered_interfaces: [
    {
      discovery_hash: "abc1",
      status: "available",
      status_code: 1,
      type: "TCPClientInterface",
      name: "Relay",
      transport: "tcp",
      transport_id: "relay-1",
      network_id: "ops",
      hops: 2,
      value: 15,
      received: "2026-02-14T12:00:00+00:00",
      last_heard: "2026-02-14T12:00:30+00:00",
      heard_count: 4,
      reachable_on: "10.0.0.8",
      port: 4242,
      config_entry: {
        name: "Relay",
        type: "TCPClientInterface",
        target_host: "10.0.0.8",
        target_port: "4242",
      },
    },
  ],
  refreshed_at: "2026-02-14T12:00:30+00:00",
} as const;

const buildFetchMock = () =>
  vi.fn(async (input: RequestInfo | URL) => {
    const requestUrl = typeof input === "string" ? input : input.toString();
    const pathname = new URL(requestUrl).pathname;
    if (pathname === "/Reticulum/Interfaces/Capabilities") {
      return new Response(JSON.stringify(capabilitiesPayload), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (pathname === "/Reticulum/Discovery") {
      return new Response(JSON.stringify(discoveryPayload), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    return new Response(JSON.stringify({ detail: "not found" }), {
      status: 404,
      headers: { "Content-Type": "application/json" },
    });
  });

describe("reticulum discovery store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it("refreshes capabilities and discovery snapshot", async () => {
    globalThis.fetch = buildFetchMock() as any;

    const store = useReticulumDiscoveryStore();
    await store.refresh();

    expect(store.capabilities.runtime_active).toBe(true);
    expect(store.capabilities.supported_interface_types).toContain("TCPClientInterface");
    expect(store.discovery.runtime_active).toBe(true);
    expect(store.discovery.discovered_interfaces).toHaveLength(1);
  });

  it("polls discovery every 15 seconds while enabled", async () => {
    vi.useFakeTimers();
    const fetchMock = buildFetchMock();
    globalThis.fetch = fetchMock as any;

    const store = useReticulumDiscoveryStore();
    await store.refresh();
    store.startPolling();

    await vi.advanceTimersByTimeAsync(15_000);
    await Promise.resolve();

    expect(fetchMock).toHaveBeenCalledTimes(4);

    store.stopPolling();
    await vi.advanceTimersByTimeAsync(15_000);
    await Promise.resolve();
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });
});
