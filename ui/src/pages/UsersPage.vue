<template>
  <div class="space-y-6">
    <BaseCard title="Clients">
      <div class="mb-4 flex gap-3">
        <BaseButton variant="secondary" @click="usersStore.fetchUsers">Refresh</BaseButton>
      </div>
      <LoadingSkeleton v-if="usersStore.loading" />
      <div v-else class="space-y-3">
        <div v-for="client in pagedClients" :key="client.id" class="rounded border border-rth-border bg-rth-panel-muted p-3">
          <div class="flex flex-wrap items-center justify-between">
            <div>
              <div class="font-semibold">{{ client.display_name || client.id }}</div>
              <div class="text-xs text-rth-muted">Destination: {{ client.id || "-" }}</div>
              <div class="text-xs text-rth-muted">Last seen: {{ formatTimestamp(client.last_seen_at) }}</div>
              <div class="text-xs text-rth-muted">Metadata: {{ formatMetadata(client.metadata) }}</div>
            </div>
            <div class="flex gap-2">
              <BaseButton variant="secondary" @click="actOnClient(client.id, 'Ban')">Ban</BaseButton>
              <BaseButton variant="secondary" @click="actOnClient(client.id, 'Unban')">Unban</BaseButton>
              <BaseButton variant="ghost" @click="actOnClient(client.id, 'Blackhole')">Blackhole</BaseButton>
            </div>
          </div>
        </div>
        <BasePagination v-model:page="clientsPage" :page-size="clientsPageSize" :total="usersStore.clients.length" />
      </div>
    </BaseCard>

    <BaseCard title="Identities">
      <LoadingSkeleton v-if="usersStore.loading" />
      <div v-else class="grid gap-3 md:grid-cols-2">
        <div v-for="identity in pagedIdentities" :key="identity.id" class="rounded border border-rth-border bg-rth-panel-muted p-3">
          <div class="font-semibold">{{ identity.display_name || identity.id }}</div>
          <div class="text-xs text-rth-muted">Status: {{ identity.status || "-" }}</div>
          <div class="text-xs text-rth-muted">Last seen: {{ formatTimestamp(identity.last_seen) }}</div>
          <div class="mt-2 flex gap-2">
            <BaseBadge v-if="identity.banned" tone="danger">Banned</BaseBadge>
            <BaseBadge v-if="identity.blackholed" tone="warning">Blackholed</BaseBadge>
          </div>
        </div>
      </div>
      <BasePagination v-model:page="identitiesPage" :page-size="identitiesPageSize" :total="usersStore.identities.length" />
    </BaseCard>

    <BaseCard title="Routing Snapshot">
      <div class="flex flex-wrap items-center gap-3">
        <BaseButton variant="secondary" @click="toggleRouting">
          {{ routingOpen ? "Hide Routing" : "Show Routing" }}
        </BaseButton>
        <BaseButton v-if="routingOpen" variant="ghost" @click="loadRouting">Refresh</BaseButton>
      </div>
      <BaseFormattedOutput v-if="routingOpen && routing" class="mt-3" :value="routing" />
      <div v-else-if="routingOpen" class="mt-3 text-xs text-rth-muted">No routing data loaded.</div>
    </BaseCard>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, watch } from "vue";
import { ref } from "vue";
import BaseBadge from "../components/BaseBadge.vue";
import BaseButton from "../components/BaseButton.vue";
import BaseCard from "../components/BaseCard.vue";
import BaseFormattedOutput from "../components/BaseFormattedOutput.vue";
import BasePagination from "../components/BasePagination.vue";
import LoadingSkeleton from "../components/LoadingSkeleton.vue";
import type { ApiError } from "../api/client";
import { endpoints } from "../api/endpoints";
import { get } from "../api/client";
import { useUsersStore } from "../stores/users";
import { useToastStore } from "../stores/toasts";
import { formatTimestamp } from "../utils/format";

const usersStore = useUsersStore();
const toastStore = useToastStore();
const routing = ref<unknown>(null);
const routingOpen = ref(false);
const clientsPage = ref(1);
const identitiesPage = ref(1);
const clientsPageSize = 6;
const identitiesPageSize = 6;

const pagedClients = computed(() => {
  const start = (clientsPage.value - 1) * clientsPageSize;
  return usersStore.clients.slice(start, start + clientsPageSize);
});

const pagedIdentities = computed(() => {
  const start = (identitiesPage.value - 1) * identitiesPageSize;
  return usersStore.identities.slice(start, start + identitiesPageSize);
});

const clientPageCount = computed(() =>
  Math.max(1, Math.ceil(usersStore.clients.length / clientsPageSize))
);
const identityPageCount = computed(() =>
  Math.max(1, Math.ceil(usersStore.identities.length / identitiesPageSize))
);

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

watch(identityPageCount, (count) => {
  if (identitiesPage.value > count) {
    identitiesPage.value = count;
  }
});

onMounted(() => {
  usersStore.fetchUsers();
});
</script>
