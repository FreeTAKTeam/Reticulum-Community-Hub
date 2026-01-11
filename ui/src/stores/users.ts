import { defineStore } from "pinia";
import { ref } from "vue";
import { endpoints } from "../api/endpoints";
import { get } from "../api/client";
import { post } from "../api/client";
import type { ClientEntry } from "../api/types";
import type { IdentityEntry } from "../api/types";

export const useUsersStore = defineStore("users", () => {
  const clients = ref<ClientEntry[]>([]);
  const identities = ref<IdentityEntry[]>([]);
  const loading = ref(false);

  const fetchUsers = async () => {
    loading.value = true;
    try {
      clients.value = await get<ClientEntry[]>(endpoints.clients);
      identities.value = await get<IdentityEntry[]>(endpoints.identities);
    } finally {
      loading.value = false;
    }
  };

  const actOnClient = async (clientId: string, action: "Ban" | "Unban" | "Blackhole") => {
    await post<void>(`${endpoints.clients}/${clientId}/${action}`);
  };

  return {
    clients,
    identities,
    loading,
    fetchUsers,
    actOnClient
  };
});
