<template>
  <div class="dashboard-hud">
    <section class="hud-banner">
      <div class="hud-brand">
        <div class="hud-brand-mark">
          <span class="hud-brand-symbol">RCH</span>
          <span class="hud-brand-subtitle">Reticulum Community Hub</span>
        </div>
        <div class="hud-brand-trace">
          <CpuTrace :samples="metrics.cpuSamples.value" :capacity="metrics.cpuCapacity.value" />
        </div>
      </div>
      <div class="hud-banner-status">
        <OnlineHelpLauncher />
        <span class="hud-chip" :class="connectionChipClass">{{ connectionLabel }}</span>
        <span class="hud-chip" :class="wsChipClass">{{ wsLabel }}</span>
        <span class="hud-url">{{ baseUrl }}</span>
      </div>
    </section>

    <section class="hud-grid">
      <aside class="hud-left">
        <div class="hud-vitals-stack">
          <div class="hud-vital-card">
            <div class="hud-vital-header">
              <span>Users</span>
              <span class="hud-cosmic-deco" aria-hidden="true">
                <span></span>
                <span></span>
                <span></span>
              </span>
            </div>
            <div class="hud-vital-value">{{ formatNumber(dashboard.status?.clients) }}</div>
            <div class="hud-sparkline">
              <span
                v-for="(bar, index) in clientsSparkline"
                :key="`clients-${index}`"
                class="hud-spark-bar"
                :style="{ height: `${bar}%` }"
              />
            </div>
          </div>
          <div class="hud-vital-card">
            <div class="hud-vital-header">
              <span>Topics</span>
              <span class="hud-cosmic-deco" aria-hidden="true">
                <span></span>
                <span></span>
                <span></span>
              </span>
            </div>
            <div class="hud-vital-value">{{ formatNumber(dashboard.status?.topics) }}</div>
            <div class="hud-sparkline">
              <span
                v-for="(bar, index) in topicsSparkline"
                :key="`topics-${index}`"
                class="hud-spark-bar"
                :style="{ height: `${bar}%` }"
              />
            </div>
          </div>
          <div class="hud-vital-card">
            <div class="hud-vital-header">
              <span>Active Missions</span>
              <span class="hud-cosmic-deco" aria-hidden="true">
                <span></span>
                <span></span>
                <span></span>
              </span>
            </div>
            <div class="hud-vital-value">{{ formatNumber(dashboard.activeMissions) }}</div>
            <div class="hud-sparkline">
              <span
                v-for="(bar, index) in missionsSparkline"
                :key="`missions-${index}`"
                class="hud-spark-bar"
                :style="{ height: `${bar}%` }"
              />
            </div>
          </div>
        </div>

        <div class="hud-panel hud-control hud-control--left">
          <div class="hud-panel-header">
            <div class="hud-panel-title">Backend Control</div>
          </div>
          <div class="hud-control-status">
            <span v-if="controlStatus" class="hud-chip" :class="controlStatusClass">
              {{ controlStatusLabel }}
            </span>
            <span v-if="controlStatus" class="hud-control-meta">PID: {{ controlStatus.pid ?? "-" }}</span>
            <span v-if="controlStatus" class="hud-control-meta">Port: {{ controlStatus.port ?? "-" }}</span>
            <span v-if="!controlStatus" class="hud-control-meta">Status unavailable.</span>
          </div>
          <div class="hud-control-actions">
            <BaseButton :disabled="controlBusy" class="hud-control-btn" icon-left="play" @click="startBackend">
              Start
            </BaseButton>
            <BaseButton
              :disabled="controlBusy"
              class="hud-control-btn hud-control-btn--stop"
              icon-left="stop"
              variant="secondary"
              @click="stopBackend"
            >
              Stop
            </BaseButton>
            <BaseButton
              :disabled="controlBusy"
              class="hud-control-btn hud-control-btn--status"
              icon-left="refresh"
              variant="secondary"
              @click="refreshControlStatus"
            >
              Status
            </BaseButton>
            <BaseButton
              :disabled="controlBusy"
              class="hud-control-btn hud-control-btn--sync"
              icon-left="refresh"
              variant="secondary"
              @click="syncBackend"
            >
              Sync
            </BaseButton>
            <BaseButton
              :disabled="controlBusy"
              class="hud-control-btn hud-control-btn--announce"
              icon-left="send"
              variant="secondary"
              @click="sendAnnounce"
            >
              Announce
            </BaseButton>
          </div>
          <div v-if="lastSyncMessage" class="hud-control-result">
            {{ lastSyncMessage }}
          </div>
        </div>
      </aside>

      <main class="hud-center">
        <div class="hud-panel hud-telemetry">
          <MessageTrafficPanel
            v-model:range="metrics.trafficRange.value"
            :traffic="metrics.traffic.value"
            :state="metrics.trafficState.value"
          />
        </div>

        <div class="hud-panel hud-events">
          <EventFeedPanel
            :events="dashboard.events"
            :identities="dashboard.eventCallsignLookup"
            :missions="dashboard.missionNames"
          >
            <template #title>
              <div class="hud-panel-title">Event Feed</div>
            </template>
          </EventFeedPanel>
        </div>
      </main>

      <aside class="hud-right">
        <div class="hud-panel hud-clock">
          <div class="hud-panel-header hud-panel-header--compact">
            <div class="hud-panel-title">Time</div>
            <span class="hud-panel-subtitle">Local node timing</span>
          </div>
          <div class="hud-clock-uptime">
            <span class="hud-clock-uptime-label">Uptime</span>
            <span class="hud-clock-uptime-value">{{ uptime }}</span>
          </div>
      <div class="hud-clock-body">
        <ReticulumClock
          width="100%"
          height="100%"
          :auto-scale="true"
          :min-scale="0.45"
          :max-scale="0.85"
          background="radial-gradient(circle at center, rgba(6, 24, 32, 0.85), rgba(5, 14, 20, 0.98))"
          padding="8px"
        />
      </div>
    </div>
  </aside>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import BaseButton from "../components/BaseButton.vue";
import OnlineHelpLauncher from "../components/OnlineHelpLauncher.vue";
import { get, post } from "../api/client";
import type { ApiError } from "../api/client";
import { endpoints } from "../api/endpoints";
import { WsClient } from "../api/ws";
import { EVENT_FEED_MAX_EVENTS, useDashboardStore } from "../stores/dashboard";
import { useConnectionStore } from "../stores/connection";
import { useToastStore } from "../stores/toasts";
import { formatNumber } from "../utils/format";
import ReticulumClock from "../components/ReticulumClock.vue";
import CpuTrace from "../components/dashboard/CpuTrace.vue";
import MessageTrafficPanel from "../components/dashboard/MessageTrafficPanel.vue";
import { useDashboardMetrics } from "../composables/useDashboardMetrics";
import EventFeedPanel from "../components/dashboard/EventFeedPanel.vue";

const dashboard = useDashboardStore();
const toastStore = useToastStore();
const connectionStore = useConnectionStore();
const metrics = useDashboardMetrics();
let pollerId: number | undefined;
let disposed = false;
let refreshing = false;
const wsClient = ref<WsClient | null>(null);
const controlStatus = ref<ControlStatus | null>(null);
const controlBusy = ref(false);
const lastSyncMessage = ref("");
let sparklineTickId: number | undefined;

interface ControlStatus {
  status?: string;
  pid?: number;
  port?: number;
  uptime_seconds?: number;
}

interface PropagationFetchResult {
  available_count?: number;
  fetched_count?: number;
  imported_count?: number;
  result?: PropagationFetchResult;
  status?: string;
  error?: string;
}

interface ControlSyncResponse {
  status?: string;
  fetch_result?: PropagationFetchResult;
}

const asRecord = (value: unknown): Record<string, unknown> =>
  value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};

const apiErrorDetail = (error: unknown): string | undefined => {
  const apiError = error as ApiError;
  if (typeof apiError?.body === "string" && apiError.body.trim()) {
    return apiError.body.trim();
  }
  const detail = asRecord(apiError?.body).detail;
  if (typeof detail === "string" && detail.trim()) {
    return detail.trim();
  }
  if (error instanceof Error && apiError?.status === undefined && error.message.trim()) {
    return error.message.trim();
  }
  return undefined;
};

const CONTROL_SYNC_TIMEOUT_MS = 70_000;

const uptime = computed(() => {
  const value = dashboard.status?.uptime;
  if (value === undefined || value === null) {
    return "-";
  }
  const hours = Math.floor(value / 3600);
  const minutes = Math.floor((value % 3600) / 60);
  return `${hours}h ${minutes}m`;
});

const controlStatusLabel = computed(() => {
  const value = controlStatus.value?.status ?? "unknown";
  return value.charAt(0).toUpperCase() + value.slice(1);
});

const controlStatusClass = computed(() => {
  const value = controlStatus.value?.status;
  if (value === "running") {
    return "hud-chip--online";
  }
  if (value === "stopping") {
    return "hud-chip--warning";
  }
  if (value === "stopped") {
    return "hud-chip--offline";
  }
  return "hud-chip--idle";
});

const connectionLabel = computed(() => connectionStore.statusLabel.toUpperCase());
const wsLabel = computed(() => connectionStore.wsLabel.toUpperCase());
const baseUrl = computed(() => connectionStore.baseUrlDisplay);

const connectionChipClass = computed(() => {
  if (connectionStore.status === "online") {
    return "hud-chip--online";
  }
  if (connectionStore.status === "offline") {
    return "hud-chip--offline";
  }
  return "hud-chip--idle";
});

const wsChipClass = computed(() => {
  if (connectionStore.wsLabel.toLowerCase() === "live") {
    return "hud-chip--live";
  }
  return "hud-chip--idle";
});


const SPARKLINE_COUNT = 12;
const SPARKLINE_MIN = 9;
const SPARKLINE_MAX = 72;
const SPARKLINE_TICK_MS = 500;

const clampSparkline = (value: number) => Math.max(SPARKLINE_MIN, Math.min(SPARKLINE_MAX, value));

const randomSparklineHeight = () => {
  return SPARKLINE_MIN + Math.floor(Math.random() * (SPARKLINE_MAX - SPARKLINE_MIN + 1));
};

const createSparklineSeed = () => {
  return Array.from({ length: SPARKLINE_COUNT }, () => randomSparklineHeight());
};

const mutateSparkline = (values: number[]) => {
  return values.map((current) => {
    if (Math.random() < 0.3) {
      return current;
    }
    const target = randomSparklineHeight();
    const blend = 0.25 + Math.random() * 0.4;
    const jitter = (Math.random() - 0.5) * 6;
    return clampSparkline(Math.round(current + (target - current) * blend + jitter));
  });
};

const clientsSparkline = ref<number[]>(createSparklineSeed());
const topicsSparkline = ref<number[]>(createSparklineSeed());
const missionsSparkline = ref<number[]>(createSparklineSeed());

const refreshSparklines = () => {
  clientsSparkline.value = mutateSparkline(clientsSparkline.value);
  topicsSparkline.value = mutateSparkline(topicsSparkline.value);
  missionsSparkline.value = mutateSparkline(missionsSparkline.value);
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

const sendAnnounce = async () => {
  controlBusy.value = true;
  try {
    const response = await post<{ status?: string }>(endpoints.controlAnnounce);
    const message = response?.status ?? "Announce sent";
    toastStore.push(message, "success");
  } catch (error) {
    toastStore.push("Announce failed", "danger");
  } finally {
    controlBusy.value = false;
  }
};

const propagationFetchToast = (response?: ControlSyncResponse): string => {
  const fetchResult = response?.fetch_result?.result ?? response?.fetch_result;
  if (fetchResult?.error) {
    return `Propagation sync requested; fetch failed: ${fetchResult.error}`;
  }
  if (typeof fetchResult?.imported_count === "number") {
    const fetched = typeof fetchResult.fetched_count === "number" ? fetchResult.fetched_count : 0;
    const available = typeof fetchResult.available_count === "number" ? fetchResult.available_count : fetched;
    return `Propagation sync requested; fetched ${fetched}/${available}, imported ${fetchResult.imported_count}`;
  }
  return response?.status === "sync_requested" ? "Propagation sync requested" : response?.status ?? "Propagation sync requested";
};

const syncBackend = async () => {
  controlBusy.value = true;
  try {
    const response = await post<ControlSyncResponse>(endpoints.controlSync, undefined, {
      timeoutMs: CONTROL_SYNC_TIMEOUT_MS
    });
    const message = propagationFetchToast(response);
    lastSyncMessage.value = message;
    toastStore.push(message, "success");
  } catch (error) {
    const detail = apiErrorDetail(error);
    const message = detail ? `Propagation sync failed: ${detail}` : "Propagation sync failed";
    lastSyncMessage.value = message;
    toastStore.push(message, "danger");
  } finally {
    controlBusy.value = false;
  }
};

onMounted(async () => {
  metrics.start();
  try {
  await dashboard.refresh();
  if (disposed) { return; }
  await refreshControlStatus();
  if (disposed) { return; }
  const ws = new WsClient(
    "/events/system",
    (payload) => {
      if (payload.type === "system.status") {
        dashboard.updateStatus(payload.data as any);
      }
      if (payload.type === "system.event") {
        dashboard.pushEvent(payload.data as any);
      }
    },
    () => {
      wsClient.value?.send({
        type: "system.subscribe",
        ts: new Date().toISOString(),
        data: {
          include_status: true,
          include_events: true,
          events_limit: EVENT_FEED_MAX_EVENTS
        }
      });
    }
  );
  wsClient.value = ws;
  ws.connect();

  pollerId = window.setInterval(() => {
    if (disposed || refreshing) { return; }
    refreshing = true;
    void dashboard.refresh().catch(error => {
      if (!disposed) { console.warn("Unable to refresh dashboard", error); }
    }).finally(() => { refreshing = false; });
  }, 30000);

  sparklineTickId = window.setInterval(() => {
    refreshSparklines();
  }, SPARKLINE_TICK_MS);

  } catch (error) {
    if (!disposed) { console.warn("Unable to initialize dashboard", error); toastStore.push("Unable to load dashboard", "danger"); }
  }
});

onUnmounted(() => {
  disposed = true;
  wsClient.value?.close();
  if (pollerId) {
    window.clearInterval(pollerId);
  }
  if (sparklineTickId) {
    window.clearInterval(sparklineTickId);
  }
  metrics.stop();
});
</script>

<style scoped src="./styles/DashboardPage.css"></style>
