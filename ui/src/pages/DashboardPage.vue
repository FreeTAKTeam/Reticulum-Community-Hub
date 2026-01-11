<template>
  <div class="space-y-6">
    <div class="grid gap-4 md:grid-cols-4">
      <BaseCard title="Uptime">
        <div class="text-2xl font-semibold">{{ uptime }}</div>
      </BaseCard>
      <BaseCard title="Clients">
        <div class="text-2xl font-semibold">{{ formatNumber(dashboard.status?.clients) }}</div>
      </BaseCard>
      <BaseCard title="Topics">
        <div class="text-2xl font-semibold">{{ formatNumber(dashboard.status?.topics) }}</div>
      </BaseCard>
      <BaseCard title="Subscribers">
        <div class="text-2xl font-semibold">{{ formatNumber(dashboard.status?.subscribers) }}</div>
      </BaseCard>
    </div>

    <BaseCard title="Telemetry">
      <div class="flex flex-wrap items-center gap-4 text-sm text-slate-300">
        <div>Total: {{ formatNumber(dashboard.status?.telemetry?.total) }}</div>
        <div>Last ingest: {{ formatTimestamp(dashboard.status?.telemetry?.last_ingest_at) }}</div>
        <BaseBadge v-if="isTelemetryStale" tone="warning">Stale</BaseBadge>
      </div>
    </BaseCard>

    <BaseCard title="Recent Events">
      <LoadingSkeleton v-if="dashboard.loading" />
      <ul v-else class="space-y-2 text-sm text-slate-200">
        <li v-for="event in dashboard.events" :key="event.id" class="rounded border border-rth-border bg-slate-900 p-3">
          <div class="flex items-center justify-between">
            <span class="font-semibold">{{ event.message }}</span>
            <span class="text-xs text-slate-400">{{ formatTimestamp(event.created_at) }}</span>
          </div>
          <div class="mt-1 text-xs text-slate-400">{{ event.category }} · {{ event.level }}</div>
        </li>
      </ul>
    </BaseCard>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { onMounted } from "vue";
import BaseBadge from "../components/BaseBadge.vue";
import BaseCard from "../components/BaseCard.vue";
import LoadingSkeleton from "../components/LoadingSkeleton.vue";
import { WsClient } from "../api/ws";
import { useDashboardStore } from "../stores/dashboard";
import { formatNumber } from "../utils/format";
import { formatTimestamp } from "../utils/format";

const dashboard = useDashboardStore();

const uptime = computed(() => {
  const value = dashboard.status?.uptime;
  if (!value) {
    return "-";
  }
  const hours = Math.floor(value / 3600);
  const minutes = Math.floor((value % 3600) / 60);
  return `${hours}h ${minutes}m`;
});

const isTelemetryStale = computed(() => {
  const last = dashboard.status?.telemetry?.last_ingest_at;
  if (!last) {
    return false;
  }
  const lastDate = new Date(last).getTime();
  if (Number.isNaN(lastDate)) {
    return false;
  }
  return Date.now() - lastDate > 10 * 60 * 1000;
});

onMounted(async () => {
  await dashboard.refresh();
  const ws = new WsClient("/events/system", (payload) => {
    if (payload.type === "system.status") {
      dashboard.updateStatus(payload.data as any);
    }
    if (payload.type === "system.event") {
      dashboard.pushEvent(payload.data as any);
    }
  });
  ws.connect();
});
</script>
