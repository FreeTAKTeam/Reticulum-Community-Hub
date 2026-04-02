import { defineStore } from "pinia";
import { ref } from "vue";
import { endpoints } from "../api/endpoints";
import { get } from "../api/client";
import { post } from "../api/client";
import { put } from "../api/client";
import type { ClientEntry } from "../api/types";
import type { IdentityEntry } from "../api/types";
import type { RemPeerEntry } from "../api/types";

type ClientApiPayload = {
  identity?: string;
  last_seen?: string;
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
  display_name: payload.display_name ?? displayNameFromMetadata(payload.metadata),
  metadata: payload.metadata,
  client_type: payload.client_type,
  announce_capabilities: payload.announce_capabilities,
  rem_mode: payload.rem_mode ?? undefined,
  is_rem_capable: payload.is_rem_capable
});

type IdentityApiPayload = {
  Identity?: string;
  DisplayName?: string | null;
  Status?: string;
  LastSeen?: string | null;
  Metadata?: Record<string, unknown>;
  IsBanned?: boolean;
  IsBlackholed?: boolean;
  ClientType?: string;
  AnnounceCapabilities?: string[];
  RemMode?: string | null;
  IsRemCapable?: boolean;
};

const fromApiIdentity = (payload: IdentityApiPayload): IdentityEntry => ({
  id: payload.Identity,
  status: payload.Status,
  last_seen: payload.LastSeen ?? undefined,
  display_name: payload.DisplayName ?? displayNameFromMetadata(payload.Metadata),
  banned: payload.IsBanned,
  blackholed: payload.IsBlackholed,
  client_type: payload.ClientType,
  announce_capabilities: payload.AnnounceCapabilities,
  rem_mode: payload.RemMode ?? undefined,
  is_rem_capable: payload.IsRemCapable
});

type RemPeersApiPayload = {
  effective_connected_mode?: boolean;
  items?: RemPeerEntry[];
};

const dedupeIdentities = (entries: IdentityEntry[]): IdentityEntry[] => {
  const byId = new Map<string, IdentityEntry>();
  const withoutId: IdentityEntry[] = [];
  entries.forEach((entry) => {
    if (!entry.id) {
      withoutId.push(entry);
      return;
    }
    byId.set(entry.id, entry);
  });
  return [...byId.values(), ...withoutId];
};

export const useUsersStore = defineStore("users", () => {
  const clients = ref<ClientEntry[]>([]);
  const identities = ref<IdentityEntry[]>([]);
  const remPeers = ref<RemPeerEntry[]>([]);
  const remConnectedMode = ref(false);
  const loading = ref(false);

  const fetchUsers = async () => {
    loading.value = true;
    try {
      const response = await get<ClientApiPayload[]>(endpoints.clients);
      clients.value = response.map(fromApiClient);
      const identityResponse = await get<IdentityApiPayload[]>(endpoints.identities);
      identities.value = dedupeIdentities(identityResponse.map(fromApiIdentity));
      const remPeersResponse = await get<RemPeersApiPayload>(endpoints.remPeers);
      remPeers.value = Array.isArray(remPeersResponse.items) ? remPeersResponse.items : [];
      remConnectedMode.value = Boolean(remPeersResponse.effective_connected_mode);
    } finally {
      loading.value = false;
    }
  };

  const actOnClient = async (clientId: string, action: "Ban" | "Unban" | "Blackhole") => {
    const identityIndex = identities.value.findIndex((entry) => entry.id === clientId);
    const previous = identityIndex >= 0 ? { ...identities.value[identityIndex] } : null;
    if (identityIndex >= 0) {
      if (action === "Ban") {
        identities.value[identityIndex].banned = true;
      }
      if (action === "Unban") {
        identities.value[identityIndex].banned = false;
        identities.value[identityIndex].blackholed = false;
      }
      if (action === "Blackhole") {
        identities.value[identityIndex].blackholed = true;
      }
    }
    try {
      const updated = await post<IdentityApiPayload>(`${endpoints.clients}/${clientId}/${action}`);
      if (identityIndex >= 0) {
        identities.value[identityIndex] = fromApiIdentity(updated);
      }
    } catch (error) {
      if (identityIndex >= 0 && previous) {
        identities.value[identityIndex] = previous;
      }
      throw error;
    }
  };

  const joinIdentity = async (identity: string) => {
    await post<boolean>(`${endpoints.rth}?identity=${encodeURIComponent(identity)}`);
  };

  const leaveIdentity = async (identity: string) => {
    await put<boolean>(`${endpoints.rth}?identity=${encodeURIComponent(identity)}`);
  };

  return {
    clients,
    identities,
    remPeers,
    remConnectedMode,
    loading,
    fetchUsers,
    actOnClient,
    joinIdentity,
    leaveIdentity
  };
});
