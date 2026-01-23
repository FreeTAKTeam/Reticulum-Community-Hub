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
      <div class="flex flex-wrap items-center gap-4 text-sm text-rth-muted">
        <div>Total: {{ formatNumber(dashboard.status?.telemetry?.total) }}</div>
        <div>Last ingest: {{ formatTimestamp(dashboard.status?.telemetry?.last_ingest_at) }}</div>
        <BaseBadge v-if="isTelemetryStale" tone="warning">Stale</BaseBadge>
      </div>
    </BaseCard>

    <BaseCard title="Backend Control">
      <div class="flex flex-wrap items-center gap-3 text-sm text-rth-muted">
        <BaseBadge v-if="controlStatus" :tone="controlStatusTone">{{ controlStatusLabel }}</BaseBadge>
        <span v-if="controlStatus">PID: {{ controlStatus.pid ?? "-" }}</span>
        <span v-if="controlStatus">Port: {{ controlStatus.port ?? "-" }}</span>
        <span v-if="!controlStatus">Status unavailable.</span>
      </div>
      <div class="mt-4 flex flex-wrap gap-2">
        <BaseButton :disabled="controlBusy" icon-left="play" @click="startBackend">Start</BaseButton>
        <BaseButton :disabled="controlBusy" variant="secondary" icon-left="stop" @click="stopBackend">Stop</BaseButton>
        <BaseButton :disabled="controlBusy" variant="secondary" icon-left="refresh" @click="refreshControlStatus">
          Status
        </BaseButton>
      </div>
    </BaseCard>

    <BaseCard title="Recent Events">
      <LoadingSkeleton v-if="dashboard.loading" />
      <div v-else class="max-h-96 overflow-y-auto pr-1 scrollbar-thin">
        <ul class="space-y-2 text-sm text-rth-text">
          <li v-for="event in dashboard.events" :key="event.id" class="rounded border border-rth-border bg-rth-panel-muted p-3">
            <div class="flex items-center justify-between">
              <span class="font-semibold">{{ event.message }}</span>
              <span class="text-xs text-rth-muted">{{ formatTimestamp(event.created_at) }}</span>
            </div>
            <div class="mt-1 text-xs text-rth-muted">{{ event.category }} - {{ event.level }}</div>
            <BaseFormattedOutput v-if="hasMetadata(event.metadata)" class="mt-2" :value="event.metadata" />
          </li>
        </ul>
      </div>
    </BaseCard>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import BaseBadge from "../components/BaseBadge.vue";
import BaseButton from "../components/BaseButton.vue";
import BaseCard from "../components/BaseCard.vue";
import BaseFormattedOutput from "../components/BaseFormattedOutput.vue";
import LoadingSkeleton from "../components/LoadingSkeleton.vue";
import { get, post } from "../api/client";
import { endpoints } from "../api/endpoints";
import { WsClient } from "../api/ws";
import { useDashboardStore } from "../stores/dashboard";
import { useToastStore } from "../stores/toasts";
import { formatNumber } from "../utils/format";
import { formatTimestamp } from "../utils/format";

const dashboard = useDashboardStore();
const toastStore = useToastStore();
let pollerId: number | undefined;
const wsClient = ref<WsClient | null>(null);
const controlStatus = ref<ControlStatus | null>(null);
const controlBusy = ref(false);

interface ControlStatus {
  status?: string;
  pid?: number;
  port?: number;
  uptime_seconds?: number;
}

const uptime = computed(() => {
  const value = dashboard.status?.uptime;
  if (value === undefined || value === null) {
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

const controlStatusLabel = computed(() => {
  const value = controlStatus.value?.status ?? "unknown";
  return value.charAt(0).toUpperCase() + value.slice(1);
});

const controlStatusTone = computed(() => {
  const value = controlStatus.value?.status;
  if (value === "running") {
    return "success";
  }
  if (value === "stopping") {
    return "warning";
  }
  if (value === "stopped") {
    return "danger";
  }
  return "neutral";
});

const hasMetadata = (value?: Record<string, unknown>) => {
  if (!value) {
    return false;
  }
  return Object.keys(value).length > 0;
};

const refreshControlStatus = async () => {
  controlBusy.value = true;
  try {
    controlStatus.value = await get<ControlStatus>(endpoints.controlStatus);
  } catch (error) {
    controlStatus.value = null;
    toastStore.push("Unable to fetch backend status", "danger");
  } finally {
    controlBusy.value = false;
  }
};

const startBackend = async () => {
  controlBusy.value = true;
  try {
    controlStatus.value = await post<ControlStatus>(endpoints.controlStart);
    toastStore.push("Backend start requested", "success");
  } catch (error) {
    toastStore.push("Backend start failed", "danger");
  } finally {
    controlBusy.value = false;
  }
};

const stopBackend = async () => {
  controlBusy.value = true;
  try {
    await post(endpoints.controlStop);
    toastStore.push("Backend stop requested", "warning");
  } catch (error) {
    toastStore.push("Backend stop failed", "danger");
  } finally {
    controlBusy.value = false;
  }
};

onMounted(async () => {
  await dashboard.refresh();
  await refreshControlStatus();
  const ws = new WsClient("/events/system", (payload) => {
    if (payload.type === "system.status") {
      dashboard.updateStatus(payload.data as any);
    }
    if (payload.type === "system.event") {
      dashboard.pushEvent(payload.data as any);
    }
  });
  ws.connect();
  wsClient.value = ws;

  pollerId = window.setInterval(() => {
    dashboard.refresh();
  }, 30000);
});

onUnmounted(() => {
  wsClient.value?.close();
  if (pollerId) {
    window.clearInterval(pollerId);
  }
});
</script>
