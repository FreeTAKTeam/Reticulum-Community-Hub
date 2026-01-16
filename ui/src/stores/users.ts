import { defineStore } from "pinia";
import { ref } from "vue";
import { endpoints } from "../api/endpoints";
import { get } from "../api/client";
import { post } from "../api/client";
import { put } from "../api/client";
import type { ClientEntry } from "../api/types";
import type { IdentityEntry } from "../api/types";

type ClientApiPayload = {
  identity?: string;
  last_seen?: string;
  metadata?: Record<string, unknown>;
  display_name?: string;
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
  metadata: payload.metadata
});

type IdentityApiPayload = {
  Identity?: string;
  DisplayName?: string | null;
  Status?: string;
  LastSeen?: string | null;
  Metadata?: Record<string, unknown>;
  IsBanned?: boolean;
  IsBlackholed?: boolean;
};

const fromApiIdentity = (payload: IdentityApiPayload): IdentityEntry => ({
  id: payload.Identity,
  status: payload.Status,
  last_seen: payload.LastSeen ?? undefined,
  display_name: payload.DisplayName ?? displayNameFromMetadata(payload.Metadata),
  banned: payload.IsBanned,
  blackholed: payload.IsBlackholed
});

export const useUsersStore = defineStore("users", () => {
  const clients = ref<ClientEntry[]>([]);
  const identities = ref<IdentityEntry[]>([]);
  const loading = ref(false);

  const fetchUsers = async () => {
    loading.value = true;
    try {
      const response = await get<ClientApiPayload[]>(endpoints.clients);
      clients.value = response.map(fromApiClient);
      const identityResponse = await get<IdentityApiPayload[]>(endpoints.identities);
      identities.value = identityResponse.map(fromApiIdentity);
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
    loading,
    fetchUsers,
    actOnClient,
    joinIdentity,
    leaveIdentity
  };
});
