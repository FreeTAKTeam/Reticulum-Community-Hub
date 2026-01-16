<template>
  <div class="space-y-6">
    <BaseCard title="Users & Routing">
      <div class="mb-4 flex flex-wrap gap-2">
        <BaseButton variant="tab" icon-left="users" :class="{ 'cui-tab-active': activeTab === 'clients' }" @click="activeTab = 'clients'">
          Users
        </BaseButton>
        <BaseButton variant="tab" icon-left="fingerprint" :class="{ 'cui-tab-active': activeTab === 'identities' }" @click="activeTab = 'identities'">
          Identities
        </BaseButton>
        <BaseButton variant="tab" icon-left="route" :class="{ 'cui-tab-active': activeTab === 'routing' }" @click="activeTab = 'routing'">
          Routing
        </BaseButton>
      </div>
      <LoadingSkeleton v-if="usersStore.loading" />
      <div v-else>
        <div v-if="activeTab === 'clients'" class="space-y-3">
          <div class="flex flex-wrap items-end gap-3">
            <div class="w-full max-w-sm">
              <BaseInput v-model="clientFilter" label="Filter users" placeholder="Filter by name or hash" />
            </div>
          </div>
          <div v-for="client in pagedClients" :key="client.id" class="rounded border border-rth-border bg-rth-panel-muted p-3">
            <div class="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div class="font-semibold">{{ resolveIdentityLabel(resolveClientDisplayName(client), client.id) }}</div>
                <div v-if="!resolveClientDisplayName(client)" class="text-xs text-rth-muted">Destination: {{ client.id || "-" }}</div>
                <div class="text-xs text-rth-muted">Last seen: {{ formatTimestamp(client.last_seen_at) }}</div>
                <div class="text-xs text-rth-muted">Metadata: {{ formatMetadata(client.metadata) }}</div>
              </div>
              <div class="flex flex-wrap gap-2">
                <BaseButton variant="danger" icon-left="ban" @click="actOnClient(client.id, 'Ban')">Ban</BaseButton>
                <BaseButton variant="success" icon-left="unban" @click="actOnClient(client.id, 'Unban')">Unban</BaseButton>
                <BaseButton variant="secondary" icon-left="blackhole" @click="actOnClient(client.id, 'Blackhole')">Blackhole</BaseButton>
                <BaseButton variant="secondary" icon-left="undo" @click="leaveClient(client.id)">Leave</BaseButton>
              </div>
            </div>
          </div>
          <BasePagination v-model:page="clientsPage" :page-size="clientsPageSize" :total="filteredClients.length" />
        </div>
        <div v-else-if="activeTab === 'identities'">
          <div class="mb-3 flex flex-wrap items-end gap-3">
            <div class="w-full max-w-sm">
              <BaseInput v-model="identityFilter" label="Filter identities" placeholder="Filter by name or hash" />
            </div>
          </div>
          <BasePagination v-model:page="identitiesPage" :page-size="identitiesPageSize" :total="filteredIdentities.length" class="mb-3" />
          <div class="grid gap-3 md:grid-cols-2">
            <div v-for="identity in pagedIdentities" :key="identity.id" class="rounded border border-rth-border bg-rth-panel-muted p-3">
              <div class="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div class="font-semibold">{{ resolveIdentityLabel(identity.display_name, identity.id) }}</div>
                  <div v-if="!identity.display_name" class="text-xs text-rth-muted">Destination: {{ identity.id || "-" }}</div>
                  <div class="text-xs text-rth-muted">Status: {{ identity.status || "-" }}</div>
                  <div class="text-xs text-rth-muted">Last seen: {{ formatTimestamp(identity.last_seen) }}</div>
                  <div class="mt-2 flex gap-2">
                    <BaseBadge v-if="identity.banned" tone="danger">Banned</BaseBadge>
                    <BaseBadge v-if="identity.blackholed" tone="warning">Blackholed</BaseBadge>
                  </div>
                </div>
                <div class="flex flex-col items-end gap-2">
                  <BaseButton
                    variant="secondary"
                    size="sm"
                    icon-left="plus"
                    :disabled="isIdentityJoined(identity.id)"
                    @click="joinIdentity(identity.id)"
                  >
                    {{ isIdentityJoined(identity.id) ? "Joined" : "Join" }}
                  </BaseButton>
                </div>
              </div>
            </div>
          </div>
          <BasePagination v-model:page="identitiesPage" :page-size="identitiesPageSize" :total="filteredIdentities.length" />
        </div>
        <div v-else>
          <BaseFormattedOutput v-if="routingOpen && routing" class="mt-3" :value="routing" />
          <div v-else-if="routingOpen" class="mt-3 text-xs text-rth-muted">No routing data loaded.</div>
          <div v-else class="text-xs text-rth-muted">Routing is hidden. Use the controls below to load a snapshot.</div>
        </div>
      </div>
      <div class="mt-4 flex justify-end gap-3">
        <BaseButton v-if="activeTab === 'clients' || activeTab === 'identities'" variant="secondary" icon-left="refresh" @click="usersStore.fetchUsers">
          Refresh
        </BaseButton>
        <BaseButton v-if="activeTab === 'routing'" variant="secondary" icon-left="route" @click="toggleRouting">
          {{ routingOpen ? "Hide Routing" : "Show Routing" }}
        </BaseButton>
        <BaseButton v-if="activeTab === 'routing' && routingOpen" variant="secondary" icon-left="refresh" @click="loadRouting">Refresh</BaseButton>
      </div>
    </BaseCard>

  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, watch } from "vue";
import { ref } from "vue";
import BaseBadge from "../components/BaseBadge.vue";
import BaseButton from "../components/BaseButton.vue";
import BaseCard from "../components/BaseCard.vue";
import BaseInput from "../components/BaseInput.vue";
import BaseFormattedOutput from "../components/BaseFormattedOutput.vue";
import BasePagination from "../components/BasePagination.vue";
import LoadingSkeleton from "../components/LoadingSkeleton.vue";
import type { ApiError } from "../api/client";
import { endpoints } from "../api/endpoints";
import { get } from "../api/client";
import { useUsersStore } from "../stores/users";
import { useToastStore } from "../stores/toasts";
import { formatTimestamp } from "../utils/format";
import { resolveIdentityLabel } from "../utils/identity";

const usersStore = useUsersStore();
const toastStore = useToastStore();
const routing = ref<unknown>(null);
const routingOpen = ref(false);
const activeTab = ref<"clients" | "identities" | "routing">("clients");
const clientsPage = ref(1);
const identitiesPage = ref(1);
const clientsPageSize = 6;
const identitiesPageSize = 6;
const identityFilter = ref("");
const clientFilter = ref("");

const filteredClients = computed(() => {
  const filter = clientFilter.value.trim().toLowerCase();
  if (!filter) {
    return usersStore.clients;
  }
  return usersStore.clients.filter((client) => {
    const displayName = resolveClientDisplayName(client) ?? "";
    const id = client.id ?? "";
    return displayName.toLowerCase().includes(filter) || id.toLowerCase().includes(filter);
  });
});

const lastSeenValue = (value?: string | null) => {
  if (!value) {
    return 0;
  }
  const timestamp = Date.parse(value);
  return Number.isNaN(timestamp) ? 0 : timestamp;
};

const sortedClients = computed(() => {
  return [...filteredClients.value].sort((a, b) => {
    const delta = lastSeenValue(b.last_seen_at) - lastSeenValue(a.last_seen_at);
    if (delta !== 0) {
      return delta;
    }
    return (a.id ?? "").localeCompare(b.id ?? "");
  });
});

const pagedClients = computed(() => {
  const start = (clientsPage.value - 1) * clientsPageSize;
  return sortedClients.value.slice(start, start + clientsPageSize);
});

const filteredIdentities = computed(() => {
  const filter = identityFilter.value.trim().toLowerCase();
  if (!filter) {
    return usersStore.identities;
  }
  return usersStore.identities.filter((identity) => {
    const displayName = identity.display_name ?? "";
    const id = identity.id ?? "";
    return displayName.toLowerCase().includes(filter) || id.toLowerCase().includes(filter);
  });
});

const sortedIdentities = computed(() => {
  return [...filteredIdentities.value].sort((a, b) => {
    const delta = lastSeenValue(b.last_seen) - lastSeenValue(a.last_seen);
    if (delta !== 0) {
      return delta;
    }
    return (a.id ?? "").localeCompare(b.id ?? "");
  });
});

const pagedIdentities = computed(() => {
  const start = (identitiesPage.value - 1) * identitiesPageSize;
  return sortedIdentities.value.slice(start, start + identitiesPageSize);
});

const identityDisplayNameById = computed(() => {
  const map = new Map<string, string>();
  usersStore.identities.forEach((identity) => {
    if (identity.id && identity.display_name) {
      map.set(identity.id, identity.display_name);
    }
  });
  return map;
});

const clientPageCount = computed(() =>
  Math.max(1, Math.ceil(filteredClients.value.length / clientsPageSize))
);
const identityPageCount = computed(() =>
  Math.max(1, Math.ceil(filteredIdentities.value.length / identitiesPageSize))
);

const clientIdentitySet = computed(() => {
  const set = new Set<string>();
  usersStore.clients.forEach((client) => {
    if (client.id) {
      set.add(client.id);
    }
  });
  return set;
});

const actOnClient = async (clientId?: string, action?: "Ban" | "Unban" | "Blackhole") => {
  if (!clientId || !action) {
    return;
  }
  try {
    await usersStore.actOnClient(clientId, action);
    toastStore.push(`Client ${action.toLowerCase()} action sent`, "success");
  } catch (error) {
    handleApiError(error, `Unable to ${action.toLowerCase()} client`);
  }
};

const leaveClient = async (clientId?: string) => {
  if (!clientId) {
    return;
  }
  try {
    await usersStore.leaveIdentity(clientId);
    await usersStore.fetchUsers();
    toastStore.push("Client left the hub", "warning");
  } catch (error) {
    handleApiError(error, "Unable to remove client");
  }
};

const joinIdentity = async (identityId?: string) => {
  if (!identityId) {
    return;
  }
  try {
    await usersStore.joinIdentity(identityId);
    await usersStore.fetchUsers();
    toastStore.push("Identity joined", "success");
  } catch (error) {
    handleApiError(error, "Unable to join identity");
  }
};

const isIdentityJoined = (identityId?: string) => {
  if (!identityId) {
    return false;
  }
  return clientIdentitySet.value.has(identityId);
};

const loadRouting = async () => {
  const response = await get<unknown>(`${endpoints.command}/DumpRouting`);
  routing.value = response;
};

const toggleRouting = async () => {
  routingOpen.value = !routingOpen.value;
  if (routingOpen.value && !routing.value) {
    await loadRouting();
  }
};

const formatMetadata = (metadata?: Record<string, unknown>) => {
  if (!metadata) {
    return "-";
  }
  const parts = Object.entries(metadata)
    .slice(0, 3)
    .map(([key, value]) => `${key}: ${String(value)}`);
  return parts.length ? parts.join(" / ") : "-";
};

const resolveClientDisplayName = (client: { id?: string; display_name?: string }) => {
  if (client.display_name) {
    return client.display_name;
  }
  if (!client.id) {
    return undefined;
  }
  return identityDisplayNameById.value.get(client.id);
};

const handleApiError = (error: unknown, fallback: string) => {
  const apiError = error as ApiError;
  if (apiError?.status === 401) {
    toastStore.push("Authentication required. Check your credentials.", "warning");
    return;
  }
  if (apiError?.status === 403) {
    toastStore.push("Forbidden. Your account lacks permission for this action.", "warning");
    return;
  }
  toastStore.push(fallback, "danger");
};

watch(clientPageCount, (count) => {
  if (clientsPage.value > count) {
    clientsPage.value = count;
  }
});

watch(clientFilter, () => {
  clientsPage.value = 1;
});

watch(identityPageCount, (count) => {
  if (identitiesPage.value > count) {
    identitiesPage.value = count;
  }
});

watch(identityFilter, () => {
  identitiesPage.value = 1;
});

onMounted(() => {
  usersStore.fetchUsers();
});
</script>
