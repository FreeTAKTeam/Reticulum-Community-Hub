<template>
  <div class="space-y-6">
    <BaseCard title="Clients">
      <div class="mb-4 flex gap-3">
        <BaseButton variant="secondary" @click="usersStore.fetchUsers">Refresh</BaseButton>
      </div>
      <LoadingSkeleton v-if="usersStore.loading" />
      <div v-else class="space-y-3">
        <div v-for="client in usersStore.clients" :key="client.id" class="rounded border border-rth-border bg-slate-900 p-3">
          <div class="flex flex-wrap items-center justify-between">
            <div>
              <div class="font-semibold">{{ client.display_name || client.id }}</div>
              <div class="text-xs text-slate-400">Last seen: {{ formatTimestamp(client.last_seen_at) }}</div>
            </div>
            <div class="flex gap-2">
              <BaseButton variant="secondary" @click="actOnClient(client.id, 'Ban')">Ban</BaseButton>
              <BaseButton variant="secondary" @click="actOnClient(client.id, 'Unban')">Unban</BaseButton>
              <BaseButton variant="ghost" @click="actOnClient(client.id, 'Blackhole')">Blackhole</BaseButton>
            </div>
          </div>
        </div>
      </div>
    </BaseCard>

    <BaseCard title="Identities">
      <LoadingSkeleton v-if="usersStore.loading" />
      <div v-else class="grid gap-3 md:grid-cols-2">
        <div v-for="identity in usersStore.identities" :key="identity.id" class="rounded border border-rth-border bg-slate-900 p-3">
          <div class="font-semibold">{{ identity.display_name || identity.id }}</div>
          <div class="text-xs text-slate-400">{{ identity.address }}</div>
          <div class="mt-2 flex gap-2">
            <BaseBadge v-if="identity.banned" tone="danger">Banned</BaseBadge>
            <BaseBadge v-if="identity.blackholed" tone="warning">Blackholed</BaseBadge>
          </div>
        </div>
      </div>
    </BaseCard>

    <BaseCard title="Routing Snapshot">
      <BaseButton variant="secondary" @click="loadRouting">Load Routing</BaseButton>
      <pre v-if="routing" class="mt-3 max-h-80 overflow-auto rounded bg-slate-900 p-3 text-xs text-slate-200">{{ routing }}</pre>
    </BaseCard>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from "vue";
import { ref } from "vue";
import BaseBadge from "../components/BaseBadge.vue";
import BaseButton from "../components/BaseButton.vue";
import BaseCard from "../components/BaseCard.vue";
import LoadingSkeleton from "../components/LoadingSkeleton.vue";
import { endpoints } from "../api/endpoints";
import { get } from "../api/client";
import { useUsersStore } from "../stores/users";
import { useToastStore } from "../stores/toasts";
import { formatTimestamp } from "../utils/format";

const usersStore = useUsersStore();
const toastStore = useToastStore();
const routing = ref("");

const actOnClient = async (clientId?: string, action?: "Ban" | "Unban" | "Blackhole") => {
  if (!clientId || !action) {
    return;
  }
  await usersStore.actOnClient(clientId, action);
  toastStore.push(`Client ${action.toLowerCase()} action sent`, "success");
};

const loadRouting = async () => {
  routing.value = await get<string>(`${endpoints.command}/DumpRouting`);
};

onMounted(() => {
  usersStore.fetchUsers();
});
</script>
