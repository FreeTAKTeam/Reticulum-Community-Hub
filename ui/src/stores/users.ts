import { useConnectionStore } from "./connection";
import { defineStore } from "pinia";
import { useBackendScope } from "../composables/useBackendScope";
import { ref } from "vue";
import { endpoints } from "../api/endpoints";
import { get } from "../api/client";
import { loadDirectory } from "../api/directory";
import { post } from "../api/client";
import { put } from "../api/client";
import type { ClientEntry } from "../api/types";
import { useIdentityDirectoryStore } from "./identity-directory";
import type { RemPeerEntry } from "../api/types";

type ClientApiPayload = {
  identity?: string;
  last_seen?: string;
  last_chat_ts_ms?: number | null;
  metadata?: Record<string, unknown>;
  display_name?: string;
  client_type?: string;
  announce_capabilities?: string[];
  rem_mode?: string | null;
  is_rem_capable?: boolean;
};

const displayNameFromMetadata = (metadata?: Record<string, unknown>): string | undefined => {
  if (!metadata) {
    return undefined;
  }
  const candidate =
    metadata.display_name ?? metadata.displayName ?? metadata.DisplayName ?? metadata.name ?? metadata.label;
  return typeof candidate === "string" ? candidate : undefined;
};

const fromApiClient = (payload: ClientApiPayload): ClientEntry => ({
  id: payload.identity,
  identity_id: payload.identity,
  last_seen_at: payload.last_seen,
  last_chat_at: typeof payload.last_chat_ts_ms === "number" && Number.isSafeInteger(payload.last_chat_ts_ms) && Math.abs(payload.last_chat_ts_ms) <= 8640000000000000
    ? new Date(payload.last_chat_ts_ms).toISOString() : undefined,
  display_name: payload.display_name ?? displayNameFromMetadata(payload.metadata),
  metadata: payload.metadata,
  client_type: payload.client_type,
  announce_capabilities: payload.announce_capabilities,
  rem_mode: payload.rem_mode ?? undefined,
  is_rem_capable: payload.is_rem_capable
});

type RemPeersApiPayload = {
  effective_connected_mode?: boolean;
  items?: RemPeerEntry[];
};

export const useUsersStore = defineStore("users", () => {
  const clients = ref<ClientEntry[]>([]);
  const remPeers = ref<RemPeerEntry[]>([]);
  const remConnectedMode = ref(false);
  const loading = ref(false);
  type Resource = "clients" | "remPeers";
  const errors = ref<Record<Resource, string | null>>({ clients: null, remPeers: null });
  const resourceLoading = ref<Record<Resource, boolean>>({ clients: false, remPeers: false });
  const backendScope = useBackendScope([clients, remPeers, remConnectedMode, loading, errors, resourceLoading]);
  const connection = useConnectionStore();
  const pending = new Map<Resource, { identity: string; promise: Promise<void> }>();

  const loadResource = (resource: Resource, work: (assertCurrent: () => void) => Promise<void>) => {
    const identity = connection.requestIdentity;
    const current = pending.get(resource);
    if (current?.identity === identity) { return current.promise; }
    const assertCurrent = backendScope();
    loading.value = true;
    resourceLoading.value[resource] = true;
    errors.value[resource] = null;
    const promise = work(assertCurrent).catch((error: unknown) => {
      assertCurrent();
      errors.value[resource] = error instanceof Error ? error.message : "Unknown loading error.";
    }).finally(() => {
      if (pending.get(resource)?.promise === promise) {
        pending.delete(resource);
        if (connection.requestIdentity === identity) { resourceLoading.value[resource] = false; }
      }
      if (connection.requestIdentity === identity) {
        loading.value = [...pending.values()].some((entry) => entry.identity === identity);
      }
    });
    pending.set(resource, { identity, promise });
    return promise;
  };

  const fetchClients = () => loadResource("clients", (assertCurrent) => loadDirectory(
    endpoints.clients, "identity", assertCurrent, (items, _total, first) => {
      const entries = items.map(fromApiClient);
      clients.value = first ? entries : [...clients.value, ...entries];
    }
  ));
  const fetchRemPeers = () => loadResource("remPeers", async (assertCurrent) => {
    const response = await get<RemPeersApiPayload>(endpoints.remPeers);
    assertCurrent();
    if (!response || !Array.isArray(response.items)) { throw new Error("Invalid REM peers response."); }
    remPeers.value = response.items;
    remConnectedMode.value = Boolean(response.effective_connected_mode);
  });
  const fetchUsers = async () => {
    await Promise.all([fetchClients(), fetchRemPeers()]);
  };

  const actOnClient = async (clientId: string, action: "Ban" | "Unban" | "Blackhole") => {
    await post<unknown>(`${endpoints.clients}/${clientId}/${action}`);
    useIdentityDirectoryStore().invalidate();
  };

  const joinIdentity = async (identity: string) => {
    await post<boolean>(`${endpoints.rth}?identity=${encodeURIComponent(identity)}`);
    useIdentityDirectoryStore().invalidate();
  };

  const leaveIdentity = async (identity: string) => {
    await put<boolean>(`${endpoints.rth}?identity=${encodeURIComponent(identity)}`);
    useIdentityDirectoryStore().invalidate();
  };

  return {
    clients,
    remPeers,
    remConnectedMode,
    loading,
    fetchUsers,
    fetchClients,
    fetchRemPeers,
    errors,
    resourceLoading,
    actOnClient,
    joinIdentity,
    leaveIdentity
  };
});
