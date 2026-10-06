import { useConnectionStore } from "./connection";
import { defineStore } from "pinia";
import { useBackendScope } from "../composables/useBackendScope";
import { ref } from "vue";
import { get } from "../api/client";
import { endpoints } from "../api/endpoints";
import type { ReticulumDiscoveryState } from "../api/types";
import type { ReticulumInterfaceCapabilities } from "../api/types";

const POLL_INTERVAL_MS = 15_000;

const fallbackCapabilities = (): ReticulumInterfaceCapabilities => ({
  runtime_active: false,
  os: "other",
  identity_hash_hex_length: 0,
  supported_interface_types: [],
  unsupported_interface_types: [],
  discoverable_interface_types: [],
  autoconnect_interface_types: [],
  rns_version: "unavailable",
});

const fallbackDiscovery = (): ReticulumDiscoveryState => ({
  runtime_active: false,
  should_autoconnect: false,
  max_autoconnected_interfaces: null,
  required_discovery_value: null,
  interface_discovery_sources: [],
  discovered_interfaces: [],
  refreshed_at: new Date().toISOString(),
});

export const useReticulumDiscoveryStore = defineStore("reticulum-discovery", () => {
  const capabilities = ref<ReticulumInterfaceCapabilities>(fallbackCapabilities());
  const discovery = ref<ReticulumDiscoveryState>(fallbackDiscovery());
  const loading = ref(false);
  const error = ref("");
  const polling = ref(false);
  const lastRefreshAt = ref<string | null>(null);
  const backendScope = useBackendScope([capabilities, discovery, loading, error, lastRefreshAt]);
  const connection = useConnectionStore();
  let pending: { identity: string; promise: Promise<void> } | undefined;

  let pollTimer: number | null = null;

  const fetchCapabilities = async () => {
    const assertCurrent = backendScope();
    const response = await get<ReticulumInterfaceCapabilities>(endpoints.reticulumInterfacesCapabilities);
    assertCurrent();
    capabilities.value = response;
    return capabilities.value;
  };

  const fetchDiscovery = async () => {
    const assertCurrent = backendScope();
    const response = await get<ReticulumDiscoveryState>(endpoints.reticulumDiscovery);
    assertCurrent();
    discovery.value = response;
    return discovery.value;
  };

  const refresh = () => {
    const identity = connection.requestIdentity;
    if (pending?.identity === identity) { return pending.promise; }
    const promise = loadDiscovery().finally(() => {
      if (pending?.promise === promise) {
        pending = undefined;
        if (connection.requestIdentity === identity) { loading.value = false; }
      }
    });
    pending = { identity, promise };
    return promise;
  };

  const loadDiscovery = async () => {
    const assertCurrent = backendScope();
    loading.value = true;
    error.value = "";
    try {
      // Keep ownership until both requests settle, even if one fails early.
      const results = await Promise.allSettled([fetchCapabilities(), fetchDiscovery()]);
      const failure = results.find((result) => result.status === "rejected");
      if (failure?.status === "rejected") { throw failure.reason; }
      assertCurrent();
      lastRefreshAt.value = new Date().toISOString();
    } catch (err) {
      if (!(err instanceof DOMException && err.name === "AbortError")) {
        assertCurrent();
        error.value = err instanceof Error ? err.message : "Failed to refresh discovery state";
      }
      throw err;
    }
  };

  const startPolling = () => {
    if (pollTimer !== null) {
      return;
    }
    polling.value = true;
    pollTimer = window.setInterval(() => {
      refresh().catch(() => undefined);
    }, POLL_INTERVAL_MS);
  };

  const stopPolling = () => {
    if (pollTimer !== null) {
      window.clearInterval(pollTimer);
      pollTimer = null;
    }
    polling.value = false;
  };

  return {
    capabilities,
    discovery,
    loading,
    error,
    polling,
    lastRefreshAt,
    refresh,
    fetchCapabilities,
    fetchDiscovery,
    startPolling,
    stopPolling,
  };
});
