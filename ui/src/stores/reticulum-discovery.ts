import { defineStore } from "pinia";
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

  let pollTimer: number | null = null;

  const fetchCapabilities = async () => {
    capabilities.value = await get<ReticulumInterfaceCapabilities>(endpoints.reticulumInterfacesCapabilities);
    return capabilities.value;
  };

  const fetchDiscovery = async () => {
    discovery.value = await get<ReticulumDiscoveryState>(endpoints.reticulumDiscovery);
    return discovery.value;
  };

  const refresh = async () => {
    loading.value = true;
    error.value = "";
    try {
      await Promise.all([fetchCapabilities(), fetchDiscovery()]);
      lastRefreshAt.value = new Date().toISOString();
    } catch (err) {
      error.value = err instanceof Error ? err.message : "Failed to refresh discovery state";
      throw err;
    } finally {
      loading.value = false;
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
