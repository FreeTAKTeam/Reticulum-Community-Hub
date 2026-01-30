<template>
  <div class="dashboard-hud">
    <section class="hud-banner">
      <div class="hud-brand">
        <div class="hud-brand-mark">
          <span class="hud-brand-symbol">RCH</span>
          <span class="hud-brand-subtitle">Reticulum Community Hub</span>
        </div>
        <div class="hud-brand-trace" />
      </div>
      <div class="hud-banner-status">
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
              <span>Clients</span>
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
              <span>Subscribers</span>
              <span class="hud-cosmic-deco" aria-hidden="true">
                <span></span>
                <span></span>
                <span></span>
              </span>
            </div>
            <div class="hud-vital-value">{{ formatNumber(dashboard.status?.subscribers) }}</div>
            <div class="hud-sparkline">
              <span
                v-for="(bar, index) in subscribersSparkline"
                :key="`subscribers-${index}`"
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
              class="hud-control-btn hud-control-btn--announce"
              icon-left="send"
              variant="secondary"
              @click="sendAnnounce"
            >
              Announce
            </BaseButton>
          </div>
        </div>
      </aside>

      <main class="hud-center">
        <div class="hud-panel hud-telemetry">
          <div class="hud-panel-header">
            <div>
              <div class="hud-panel-title">Global Telemetry Stream</div>
              <div class="hud-panel-meta">
                <span>Total: {{ formatNumber(dashboard.status?.telemetry?.total) }}</span>
                <span>Last ingest: {{ formatTimestamp(dashboard.status?.telemetry?.last_ingest_at) }}</span>
              </div>
            </div>
            <span v-if="isTelemetryStale" class="hud-pill hud-pill--warning">Stale</span>
          </div>
          <div class="hud-stream" :style="{ '--bucket-count': bucketCount }">
            <div class="hud-stream-legend">
              <span class="hud-legend-item hud-legend-item--ingest">Ingest</span>
              <span class="hud-legend-item hud-legend-item--motion">Motion</span>
              <span class="hud-legend-item hud-legend-item--throughput">Transport</span>
              <span class="hud-legend-window">24H WINDOW</span>
            </div>
            <div class="hud-stream-grid hud-stream-grid--ingest">
              <span
                v-for="(value, index) in ingestSeries"
                :key="`ingest-${index}`"
                class="hud-stream-bar hud-stream-bar--ingest"
                :style="{ height: `${value}%` }"
              />
            </div>
            <div class="hud-stream-grid hud-stream-grid--motion">
              <span
                v-for="(value, index) in motionSeries"
                :key="`motion-${index}`"
                class="hud-stream-bar hud-stream-bar--motion"
                :style="{ height: `${value}%` }"
              />
            </div>
            <div class="hud-stream-grid hud-stream-grid--throughput">
              <span
                v-for="(value, index) in throughputSeries"
                :key="`throughput-${index}`"
                class="hud-stream-bar hud-stream-bar--throughput"
                :style="{ height: `${value}%` }"
              />
            </div>
            <div class="hud-stream-grid hud-stream-grid--markers">
              <span
                v-for="(value, index) in markerSeries"
                :key="`marker-${index}`"
                class="hud-stream-marker"
                :style="{ opacity: value ? 1 : 0 }"
              />
            </div>
            <div class="hud-stream-axis">
              <span
                v-for="(tick, index) in axisTicks"
                :key="`tick-${index}`"
                class="hud-stream-tick"
                :style="{ left: `${tick.left}%` }"
              >
                <span class="hud-stream-tick-line" />
                <span class="hud-stream-tick-label">{{ tick.label }}</span>
              </span>
            </div>
          </div>
        </div>

        <div class="hud-panel hud-events">
          <div class="hud-panel-header hud-panel-header--compact">
            <div class="hud-panel-title">Event Feed</div>
            <span class="hud-panel-subtitle">Realtime system activity</span>
          </div>
          <LoadingSkeleton v-if="dashboard.loading" />
          <div v-else class="hud-events-body">
            <div v-if="!dashboard.events.length" class="hud-empty">No events yet.</div>
            <table v-else class="hud-events-table">
              <thead>
                <tr>
                  <th>Event</th>
                  <th>Type</th>
                  <th>Time</th>
                  <th class="hud-events-cell--action">Details</th>
                </tr>
              </thead>
              <tbody>
                <template v-for="(event, index) in dashboard.events" :key="eventRowKey(event, index)">
                  <tr class="hud-events-row">
                    <td class="hud-events-cell hud-events-cell--message">
                      <span class="hud-event-title">{{ event.message }}</span>
                    </td>
                    <td class="hud-events-cell hud-events-cell--meta">
                      <span class="hud-event-tag">{{ event.category }}</span>
                      <span class="hud-event-tag hud-event-tag--level">{{ event.level }}</span>
                    </td>
                    <td class="hud-events-cell hud-events-cell--time">
                      {{ formatTimestamp(event.created_at) }}
                    </td>
                    <td class="hud-events-cell hud-events-cell--action">
                      <button
                        type="button"
                        class="hud-events-toggle"
                        :disabled="!hasMetadata(event.metadata)"
                        @click="toggleEventDetails(eventRowKey(event, index))"
                      >
                        <span>{{ isEventExpanded(eventRowKey(event, index)) ? "Hide" : "Details" }}</span>
                        <span
                          class="hud-events-toggle-icon"
                          :class="{ 'hud-events-toggle-icon--open': isEventExpanded(eventRowKey(event, index)) }"
                        />
                      </button>
                    </td>
                  </tr>
                  <tr v-if="isEventExpanded(eventRowKey(event, index))" class="hud-events-details-row">
                    <td colspan="4">
                      <div class="hud-events-details">
                        <BaseFormattedOutput class="hud-event-json" :value="event.metadata" />
                      </div>
                    </td>
                  </tr>
                </template>
              </tbody>
            </table>
          </div>
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
import { computed, onMounted, onUnmounted, ref } from "vue";
import BaseButton from "../components/BaseButton.vue";
import BaseFormattedOutput from "../components/BaseFormattedOutput.vue";
import LoadingSkeleton from "../components/LoadingSkeleton.vue";
import { get, post } from "../api/client";
import { endpoints } from "../api/endpoints";
import { WsClient } from "../api/ws";
import { useDashboardStore } from "../stores/dashboard";
import { useConnectionStore } from "../stores/connection";
import { useToastStore } from "../stores/toasts";
import { formatNumber } from "../utils/format";
import { formatTimestamp } from "../utils/format";
import ReticulumClock from "../components/ReticulumClock.vue";
import type { EventEntry } from "../api/types";

const dashboard = useDashboardStore();
const toastStore = useToastStore();
const connectionStore = useConnectionStore();
let pollerId: number | undefined;
const wsClient = ref<WsClient | null>(null);
const telemetryWsClient = ref<WsClient | null>(null);
const controlStatus = ref<ControlStatus | null>(null);
const controlBusy = ref(false);
let telemetryTickId: number | undefined;
const telemetrySubscribed = ref(false);
const expandedEvents = ref<Record<string, boolean>>({});

interface ControlStatus {
  status?: string;
  pid?: number;
  port?: number;
  uptime_seconds?: number;
}

interface TelemetryBucket {
  count: number;
  motion: number;
  throughput: number;
  markers: number;
}

const HOURS_RANGE = 24;
const BUCKET_MINUTES = 15;
const BUCKET_MS = BUCKET_MINUTES * 60 * 1000;
const BUCKET_COUNT = (HOURS_RANGE * 60) / BUCKET_MINUTES;
const RANGE_MS = HOURS_RANGE * 60 * 60 * 1000;

const bucketCount = BUCKET_COUNT;
const telemetryBuckets = ref<TelemetryBucket[]>([]);
const bucketStart = ref<number>(0);
const nowMs = ref(Date.now());

const createEmptyBucket = (): TelemetryBucket => ({
  count: 0,
  motion: 0,
  throughput: 0,
  markers: 0
});

const resetBuckets = (anchorMs: number) => {
  const base = Math.floor((anchorMs - RANGE_MS) / BUCKET_MS) * BUCKET_MS;
  bucketStart.value = base;
  telemetryBuckets.value = Array.from({ length: BUCKET_COUNT }, createEmptyBucket);
};

const shiftWindow = (anchorMs: number) => {
  if (!bucketStart.value) {
    resetBuckets(anchorMs);
    return;
  }
  if (anchorMs < bucketStart.value) {
    resetBuckets(anchorMs);
    return;
  }
  const end = bucketStart.value + RANGE_MS;
  if (anchorMs < end) {
    return;
  }
  const newStart = Math.floor((anchorMs - RANGE_MS) / BUCKET_MS) * BUCKET_MS;
  const shift = Math.min(BUCKET_COUNT, Math.floor((newStart - bucketStart.value) / BUCKET_MS));
  if (shift > 0) {
    telemetryBuckets.value = telemetryBuckets.value
      .slice(shift)
      .concat(Array.from({ length: shift }, createEmptyBucket));
    bucketStart.value = newStart;
  }
};

const toNumber = (value: unknown) => {
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : undefined;
  }
  if (typeof value === "string") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : undefined;
  }
  return undefined;
};

const calcMotion = (telemetry: Record<string, unknown>) => {
  const location = telemetry.location as Record<string, unknown> | undefined;
  const speed = location ? toNumber(location.speed ?? location.velocity ?? location.v) ?? 0 : 0;
  const accel = telemetry.acceleration as Record<string, unknown> | number[] | undefined;
  let accelMag = 0;
  if (Array.isArray(accel)) {
    const x = toNumber(accel[0]) ?? 0;
    const y = toNumber(accel[1]) ?? 0;
    const z = toNumber(accel[2]) ?? 0;
    accelMag = Math.sqrt(x * x + y * y + z * z);
  } else if (accel && typeof accel === "object") {
    const x = toNumber(accel.x ?? accel.X) ?? 0;
    const y = toNumber(accel.y ?? accel.Y) ?? 0;
    const z = toNumber(accel.z ?? accel.Z) ?? 0;
    accelMag = Math.sqrt(x * x + y * y + z * z);
  }
  return Math.max(speed, accelMag);
};

const calcThroughput = (telemetry: Record<string, unknown>) => {
  const rns = telemetry.rns_transport as Record<string, unknown> | undefined;
  if (!rns || typeof rns !== "object") {
    return 0;
  }
  const rx = toNumber(rns.speed_rx ?? rns.speed_rx_inst ?? rns.rxs) ?? 0;
  const tx = toNumber(rns.speed_tx ?? rns.speed_tx_inst ?? rns.txs) ?? 0;
  return rx + tx;
};

const hasMarker = (telemetry: Record<string, unknown>) => {
  const custom = telemetry.custom as Record<string, unknown> | undefined;
  if (!custom || typeof custom !== "object") {
    return false;
  }
  const marker = (custom as Record<string, unknown>).marker;
  if (Array.isArray(marker)) {
    return marker.some((entry) => Boolean(entry));
  }
  return Boolean(marker);
};

const resolveTimestampMs = (entry: Record<string, unknown>) => {
  const timestamp = entry.timestamp;
  if (typeof timestamp === "number" && Number.isFinite(timestamp)) {
    return timestamp * 1000;
  }
  const createdAt = entry.created_at;
  if (typeof createdAt === "string") {
    const parsed = Date.parse(createdAt);
    if (!Number.isNaN(parsed)) {
      return parsed;
    }
  }
  return Date.now();
};

const pushTelemetryEntry = (entry: Record<string, unknown>) => {
  const timestampMs = resolveTimestampMs(entry);
  shiftWindow(timestampMs);
  const index = Math.floor((timestampMs - bucketStart.value) / BUCKET_MS);
  if (index < 0 || index >= BUCKET_COUNT) {
    return;
  }
  const telemetry = (entry.telemetry ?? entry.data ?? {}) as Record<string, unknown>;
  const bucket = telemetryBuckets.value[index];
  bucket.count += 1;
  bucket.motion = Math.max(bucket.motion, calcMotion(telemetry));
  bucket.throughput = Math.max(bucket.throughput, calcThroughput(telemetry));
  if (hasMarker(telemetry)) {
    bucket.markers += 1;
  }
};

const ingestSeries = computed(() => {
  const values = telemetryBuckets.value.map((bucket) => bucket.count);
  const max = Math.max(1, ...values);
  return values.map((value) => Math.min(100, (value / max) * 100));
});

const motionSeries = computed(() => {
  const values = telemetryBuckets.value.map((bucket) => bucket.motion);
  const max = Math.max(1, ...values);
  return values.map((value) => Math.min(100, (value / max) * 100));
});

const throughputSeries = computed(() => {
  const values = telemetryBuckets.value.map((bucket) => bucket.throughput);
  const max = Math.max(1, ...values);
  return values.map((value) => Math.min(100, (value / max) * 100));
});

const markerSeries = computed(() => telemetryBuckets.value.map((bucket) => bucket.markers));

const axisTicks = computed(() => {
  const now = nowMs.value;
  return Array.from({ length: 5 }, (_, idx) => {
    const hoursAgo = (4 - idx) * 6;
    const tickTime = new Date(now - hoursAgo * 60 * 60 * 1000);
    const label = tickTime.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    return {
      label,
      left: (idx / 4) * 100
    };
  });
});

const sendTelemetrySubscribe = () => {
  if (!telemetryWsClient.value || telemetrySubscribed.value) {
    return;
  }
  telemetryWsClient.value.send({
    type: "telemetry.subscribe",
    ts: new Date().toISOString(),
    data: {
      since: Math.floor((Date.now() - RANGE_MS) / 1000),
      follow: true
    }
  });
  telemetrySubscribed.value = true;
};

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

const hasMetadata = (value?: Record<string, unknown>) => {
  if (!value) {
    return false;
  }
  return Object.keys(value).length > 0;
};

const eventRowKey = (event: EventEntry, index: number) => {
  return event.id ?? event.created_at ?? `event-${index}`;
};

const isEventExpanded = (key: string) => Boolean(expandedEvents.value[key]);

const toggleEventDetails = (key: string) => {
  expandedEvents.value[key] = !expandedEvents.value[key];
};

const clientsSparkline = [18, 24, 12, 38, 26, 46, 20, 54, 16, 34, 22, 42];
const topicsSparkline = [10, 18, 28, 20, 34, 26, 48, 22, 36, 18, 30, 24];
const subscribersSparkline = [14, 30, 20, 44, 24, 36, 28, 52, 18, 40, 22, 34];
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

onMounted(async () => {
  await dashboard.refresh();
  await refreshControlStatus();
  resetBuckets(Date.now());
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

  const telemetryWs = new WsClient(
    "/telemetry/stream",
    (payload) => {
      if (payload.type === "auth.ok") {
        sendTelemetrySubscribe();
        return;
      }
      if (payload.type === "telemetry.snapshot") {
        const entries = (payload.data as { entries?: Record<string, unknown>[] })?.entries ?? [];
        resetBuckets(Date.now());
        entries.forEach((entry) => pushTelemetryEntry(entry));
        return;
      }
      if (payload.type === "telemetry.update") {
        const entry = (payload.data as { entry?: Record<string, unknown> })?.entry ?? payload.data;
        if (entry && typeof entry === "object") {
          pushTelemetryEntry(entry as Record<string, unknown>);
        }
      }
    },
    () => {
      window.setTimeout(() => {
        sendTelemetrySubscribe();
      }, 250);
    }
  );
  telemetryWs.connect();
  telemetryWsClient.value = telemetryWs;

  pollerId = window.setInterval(() => {
    dashboard.refresh();
  }, 30000);

  telemetryTickId = window.setInterval(() => {
    const now = Date.now();
    nowMs.value = now;
    shiftWindow(now);
  }, 60000);
});

onUnmounted(() => {
  wsClient.value?.close();
  telemetryWsClient.value?.close();
  if (pollerId) {
    window.clearInterval(pollerId);
  }
  if (telemetryTickId) {
    window.clearInterval(telemetryTickId);
  }
});
</script>

<style scoped>
.dashboard-hud {
  --hud-cyan: #38f4ff;
  --hud-amber: #ff9b2f;
  --hud-green: #4ddf8c;
  --hud-red: #ff5d6e;
  --hud-text: #e7f4ff;
  --hud-muted: rgba(231, 244, 255, 0.6);
  --hud-panel: rgba(6, 18, 24, 0.88);
  --hud-border: rgba(56, 244, 255, 0.35);
  --hud-border-strong: rgba(56, 244, 255, 0.65);
  --hud-shadow: 0 0 25px rgba(56, 244, 255, 0.18);
  --hud-grid: rgba(56, 244, 255, 0.06);
  --hud-pad: clamp(6px, 1.2vh, 10px);
  --hud-gap: clamp(8px, 1.2vh, 14px);
  --hud-panel-pad: clamp(10px, 1.2vh, 14px);

  position: relative;
  padding: var(--hud-pad);
  min-height: 0;
  height: 100%;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--hud-gap);
  color: var(--hud-text);
  background: radial-gradient(120% 120% at 50% 0%, rgba(10, 22, 32, 0.95) 0%, #05080f 55%, #04070d 100%);
  border-radius: 18px;
  overflow: hidden;
}

.dashboard-hud::before {
  content: "";
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(135deg, rgba(255, 255, 255, 0.03) 0%, transparent 55%),
    linear-gradient(rgba(56, 244, 255, 0.08) 1px, transparent 1px),
    linear-gradient(90deg, rgba(56, 244, 255, 0.06) 1px, transparent 1px);
  background-size: 100% 100%, 48px 48px, 48px 48px;
  opacity: 0.65;
  pointer-events: none;
}

.dashboard-hud > * {
  position: relative;
  z-index: 1;
}

.hud-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: clamp(8px, 1.2vh, 12px) clamp(12px, 1.6vh, 16px);
  border-radius: 16px;
  border: 1px solid var(--hud-border-strong);
  background: linear-gradient(90deg, rgba(7, 20, 28, 0.95), rgba(9, 28, 38, 0.85));
  box-shadow: var(--hud-shadow);
}

.hud-brand {
  display: flex;
  align-items: center;
  gap: 16px;
  min-width: 0;
}

.hud-brand-mark {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.hud-brand-symbol {
  font-family: "Orbitron", "Rajdhani", sans-serif;
  font-size: clamp(1.2rem, 2.2vh, 1.6rem);
  letter-spacing: 0.2em;
  color: var(--hud-cyan);
}

.hud-brand-subtitle {
  font-size: clamp(0.6rem, 1.2vh, 0.75rem);
  letter-spacing: 0.24em;
  text-transform: uppercase;
  color: var(--hud-muted);
}

.hud-brand-trace {
  flex: 1;
  height: 2px;
  min-width: 80px;
  background: linear-gradient(90deg, var(--hud-cyan), transparent);
  opacity: 0.7;
}

.hud-banner-status {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.hud-chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid var(--hud-border);
  font-size: 0.6rem;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  font-family: "Orbitron", "Rajdhani", sans-serif;
  background: rgba(7, 20, 28, 0.8);
}

.hud-chip--online {
  color: var(--hud-green);
  border-color: rgba(77, 223, 140, 0.8);
  box-shadow: 0 0 10px rgba(77, 223, 140, 0.35);
}

.hud-chip--offline {
  color: var(--hud-red);
  border-color: rgba(255, 93, 110, 0.7);
}

.hud-chip--idle {
  color: rgba(231, 244, 255, 0.7);
}

.hud-chip--live {
  color: var(--hud-amber);
  border-color: rgba(255, 155, 47, 0.7);
  background: rgba(33, 22, 8, 0.8);
}

.hud-chip--warning {
  color: var(--hud-amber);
  border-color: rgba(255, 155, 47, 0.8);
}

.hud-url {
  font-size: 0.7rem;
  font-family: "JetBrains Mono", "Cascadia Mono", monospace;
  color: var(--hud-muted);
}

.hud-grid {
  display: grid;
  grid-template-columns: minmax(220px, 0.95fr) minmax(0, 2.4fr) minmax(260px, 1.2fr);
  gap: clamp(8px, 1vh, 12px);
  align-items: stretch;
  flex: 1;
  min-height: 0;
}

.hud-left {
  display: flex;
  flex-direction: column;
  gap: clamp(8px, 1vh, 12px);
  min-height: 0;
}

.hud-vitals-stack {
  display: flex;
  flex-direction: column;
  gap: clamp(8px, 1vh, 12px);
  flex: 1;
  min-height: 0;
}

.hud-vital-card {
  position: relative;
  padding: clamp(8px, 1.1vh, 10px) clamp(10px, 1.3vh, 12px);
  border-radius: 12px;
  background: var(--hud-panel);
  border: 1px solid var(--hud-border);
  box-shadow: inset 0 0 20px rgba(4, 20, 28, 0.8);
  min-height: clamp(78px, 9.5vh, 96px);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  flex: 1 1 0;
}

.hud-vital-card::after {
  content: "";
  position: absolute;
  top: 10px;
  right: 12px;
  width: 28px;
  height: 6px;
  background: linear-gradient(90deg, var(--hud-amber), transparent);
  opacity: 0.8;
}

.hud-vital-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 0.65rem;
  letter-spacing: 0.24em;
  text-transform: uppercase;
  color: var(--hud-muted);
  font-family: "Orbitron", "Rajdhani", sans-serif;
}

.hud-vital-tag {
  padding: 2px 6px;
  border-radius: 999px;
  border: 1px solid rgba(255, 155, 47, 0.7);
  color: var(--hud-amber);
  font-size: 0.55rem;
}

.hud-vital-tag--cyan {
  border-color: rgba(56, 244, 255, 0.6);
  color: var(--hud-cyan);
}

.hud-vital-tag--amber {
  border-color: rgba(255, 155, 47, 0.7);
  color: var(--hud-amber);
}

.hud-cosmic-deco {
  display: inline-flex;
  gap: 6px;
  align-items: center;
}

.hud-cosmic-deco span {
  width: 14px;
  height: 6px;
  border-radius: 2px;
  background: linear-gradient(90deg, rgba(255, 155, 47, 0.95), rgba(255, 155, 47, 0.35));
  box-shadow: 0 0 8px rgba(255, 155, 47, 0.45);
}

.hud-vital-value {
  font-size: clamp(2.2rem, 5.2vh, 3.5rem);
  font-family: "Orbitron", "Rajdhani", sans-serif;
  letter-spacing: 0.08em;
  color: #ffffff;
  text-shadow:
    0 0 5px rgba(56, 244, 255, 0.9),
    0 0 10px rgba(56, 244, 255, 0.7),
    0 0 20px rgba(56, 244, 255, 0.6),
    0 0 40px rgba(56, 244, 255, 0.35);
}

.hud-sparkline {
  display: flex;
  align-items: flex-end;
  gap: 4px;
  height: clamp(22px, 3.5vh, 32px);
}

.hud-spark-bar {
  width: 4px;
  border-radius: 4px 4px 0 0;
  background: linear-gradient(180deg, var(--hud-cyan), rgba(56, 244, 255, 0.2));
  opacity: 0.7;
}

.hud-center {
  display: grid;
  grid-template-rows: minmax(140px, 0.45fr) minmax(0, 1fr);
  gap: clamp(10px, 1.2vh, 14px);
  min-height: 0;
}

.hud-panel {
  position: relative;
  padding: var(--hud-panel-pad);
  border-radius: 14px;
  border: 1px solid var(--hud-border);
  background: var(--hud-panel);
  box-shadow: inset 0 0 30px rgba(4, 20, 28, 0.8);
  overflow: hidden;
}

.hud-panel::before {
  content: "";
  position: absolute;
  top: 0;
  right: 16px;
  width: 52px;
  height: 4px;
  background: linear-gradient(90deg, var(--hud-amber), transparent);
  opacity: 0.8;
}

.hud-panel-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.hud-panel-header--compact {
  align-items: center;
  margin-bottom: clamp(6px, 0.8vh, 10px);
}

.hud-panel-title {
  font-family: "Orbitron", "Rajdhani", sans-serif;
  font-size: clamp(0.7rem, 1.2vh, 0.8rem);
  letter-spacing: 0.26em;
  text-transform: uppercase;
  color: var(--hud-text);
}

.hud-panel-subtitle {
  font-size: clamp(0.6rem, 1vh, 0.7rem);
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: rgba(231, 244, 255, 0.5);
}

.hud-panel-meta {
  display: flex;
  gap: 12px;
  margin-top: clamp(4px, 0.8vh, 8px);
  font-size: clamp(0.62rem, 1.1vh, 0.72rem);
  color: var(--hud-muted);
  flex-wrap: wrap;
}

.hud-pill {
  font-size: 0.6rem;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid var(--hud-border);
  color: var(--hud-text);
  background: rgba(8, 18, 26, 0.8);
}

.hud-pill--warning {
  border-color: rgba(255, 155, 47, 0.7);
  color: var(--hud-amber);
}

.hud-stream {
  position: relative;
  margin-top: clamp(8px, 1.1vh, 14px);
  height: clamp(110px, 16vh, 170px);
  border-radius: 12px;
  border: 1px solid rgba(56, 244, 255, 0.2);
  background: linear-gradient(180deg, rgba(6, 24, 32, 0.85), rgba(6, 12, 18, 0.95));
  overflow: hidden;
  box-shadow: inset 0 0 20px rgba(4, 18, 24, 0.8);
}

.hud-stream::before {
  content: "";
  position: absolute;
  inset: 0;
  background:
    linear-gradient(rgba(56, 244, 255, 0.08) 1px, transparent 1px),
    linear-gradient(90deg, rgba(56, 244, 255, 0.05) 1px, transparent 1px);
  background-size: 48px 48px, 48px 48px;
  opacity: 0.4;
  pointer-events: none;
}

.hud-stream-legend {
  position: absolute;
  top: 10px;
  left: 12px;
  right: 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 0.6rem;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  font-family: "Orbitron", "Rajdhani", sans-serif;
  color: rgba(231, 244, 255, 0.6);
  z-index: 2;
}

.hud-legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.hud-legend-item::before {
  content: "";
  width: 16px;
  height: 6px;
  border-radius: 999px;
  background: currentColor;
  box-shadow: 0 0 10px currentColor;
}

.hud-legend-item--ingest {
  color: var(--hud-cyan);
}

.hud-legend-item--motion {
  color: rgba(56, 244, 255, 0.65);
}

.hud-legend-item--throughput {
  color: var(--hud-amber);
}

.hud-legend-window {
  font-size: 0.55rem;
  color: rgba(231, 244, 255, 0.45);
}

.hud-stream-grid {
  position: absolute;
  left: 12px;
  right: 12px;
  top: 32px;
  bottom: 26px;
  display: grid;
  grid-template-columns: repeat(var(--bucket-count), minmax(0, 1fr));
  gap: 2px;
  align-items: end;
  pointer-events: none;
}

.hud-stream-grid--motion {
  opacity: 0.7;
}

.hud-stream-grid--throughput {
  opacity: 0.5;
}

.hud-stream-grid--markers {
  top: 18px;
  bottom: auto;
  height: 8px;
  align-items: center;
  opacity: 0.9;
}

.hud-stream-bar {
  width: 100%;
  border-radius: 4px 4px 0 0;
  background: linear-gradient(180deg, rgba(56, 244, 255, 0.85), rgba(56, 244, 255, 0.2));
}

.hud-stream-bar--ingest {
  background: linear-gradient(180deg, var(--hud-cyan), rgba(56, 244, 255, 0.2));
}

.hud-stream-bar--motion {
  justify-self: center;
  width: 2px;
  border-radius: 999px;
  background: rgba(56, 244, 255, 0.7);
  box-shadow: 0 0 12px rgba(56, 244, 255, 0.6);
}

.hud-stream-bar--throughput {
  background: linear-gradient(180deg, rgba(255, 155, 47, 0.9), rgba(255, 155, 47, 0.15));
}

.hud-stream-marker {
  width: 100%;
  height: 6px;
  border-radius: 999px;
  background: var(--hud-amber);
  box-shadow: 0 0 10px rgba(255, 155, 47, 0.6);
  transition: opacity 0.2s ease;
}

.hud-stream-axis {
  position: absolute;
  left: 12px;
  right: 12px;
  bottom: 6px;
  height: 20px;
  z-index: 2;
}

.hud-stream-tick {
  position: absolute;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  transform: translateX(-50%);
  font-size: 0.55rem;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: rgba(231, 244, 255, 0.55);
  font-family: "JetBrains Mono", "Cascadia Mono", monospace;
}

.hud-stream-tick-line {
  width: 1px;
  height: 6px;
  background: rgba(56, 244, 255, 0.35);
}

.hud-events {
  min-height: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.hud-events-body {
  margin-top: clamp(6px, 1vh, 8px);
  overflow-y: auto;
  padding-right: 6px;
  flex: 1;
  min-height: 0;
}

.hud-events-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.hud-event-card {
  border-radius: 10px;
  border: 1px solid rgba(56, 244, 255, 0.2);
  background: rgba(7, 20, 28, 0.8);
  padding: 12px;
  box-shadow: inset 0 0 20px rgba(4, 18, 24, 0.8);
}

.hud-event-header {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: baseline;
}

.hud-event-title {
  font-weight: 600;
  font-size: clamp(0.78rem, 1.4vh, 0.85rem);
  color: #ffffff;
}

.hud-event-time {
  font-size: clamp(0.6rem, 1.1vh, 0.7rem);
  color: var(--hud-muted);
}

.hud-event-meta {
  margin-top: 6px;
  font-size: 0.7rem;
  color: rgba(231, 244, 255, 0.5);
}

.hud-event-json {
  margin-top: 8px;
}

.hud-events-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0 6px;
  font-size: 0.7rem;
  table-layout: fixed;
}

.hud-events-table thead th {
  text-align: left;
  font-size: 0.55rem;
  letter-spacing: 0.24em;
  text-transform: uppercase;
  color: rgba(231, 244, 255, 0.45);
  padding: 0 8px 4px;
  font-family: "Orbitron", "Rajdhani", sans-serif;
}

.hud-events-table thead th.hud-events-cell--action {
  text-align: right;
}

.hud-events-row td {
  padding: 8px 10px;
  background: rgba(7, 20, 28, 0.82);
  border-top: 1px solid rgba(56, 244, 255, 0.18);
  border-bottom: 1px solid rgba(56, 244, 255, 0.18);
}

.hud-events-row td:first-child {
  border-left: 1px solid rgba(56, 244, 255, 0.18);
  border-radius: 10px 0 0 10px;
}

.hud-events-row td:last-child {
  border-right: 1px solid rgba(56, 244, 255, 0.18);
  border-radius: 0 10px 10px 0;
}

.hud-events-cell--message {
  width: 50%;
}

.hud-events-cell--message .hud-event-title {
  display: block;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.hud-events-cell--meta {
  width: 22%;
  white-space: nowrap;
}

.hud-events-cell--time {
  width: 20%;
  font-family: "JetBrains Mono", "Cascadia Mono", monospace;
  font-size: 0.58rem;
  color: var(--hud-muted);
  white-space: nowrap;
}

.hud-events-cell--action {
  width: 8%;
  text-align: right;
}

.hud-event-tag {
  display: inline-flex;
  align-items: center;
  padding: 2px 6px;
  border-radius: 999px;
  border: 1px solid rgba(56, 244, 255, 0.3);
  color: rgba(231, 244, 255, 0.7);
  font-size: 0.5rem;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  margin-right: 6px;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
}

.hud-event-tag--level {
  border-color: rgba(255, 155, 47, 0.4);
  color: var(--hud-amber);
}

.hud-events-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 6px;
  border-radius: 999px;
  border: 1px solid rgba(56, 244, 255, 0.3);
  background: rgba(8, 18, 26, 0.7);
  color: var(--hud-cyan);
  font-size: 0.5rem;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  font-family: "Orbitron", "Rajdhani", sans-serif;
  cursor: pointer;
  transition: all 0.2s ease;
}

.hud-events-toggle:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.hud-events-toggle-icon {
  width: 10px;
  height: 10px;
  border-right: 2px solid currentColor;
  border-bottom: 2px solid currentColor;
  transform: rotate(45deg);
  transition: transform 0.2s ease;
}

.hud-events-toggle-icon--open {
  transform: rotate(-135deg);
}

.hud-events-details-row td {
  padding: 0;
  border: none;
}

.hud-events-details {
  margin: 0 10px 10px;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid rgba(56, 244, 255, 0.2);
  background: rgba(6, 18, 26, 0.85);
  box-shadow: inset 0 0 18px rgba(4, 18, 24, 0.8);
}

.hud-empty {
  font-size: 0.8rem;
  color: var(--hud-muted);
  padding: 12px 0;
}

.hud-right {
  display: flex;
  flex-direction: column;
  gap: clamp(10px, 1.2vh, 14px);
  min-height: 0;
}

.hud-control {
  min-height: clamp(170px, 20vh, 210px);
}

.hud-control--left {
  margin-top: auto;
}

.hud-control-status {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 8px;
  font-size: 0.75rem;
  color: var(--hud-muted);
}

.hud-control-meta {
  font-family: "JetBrains Mono", "Cascadia Mono", monospace;
}

.hud-control-actions {
  margin-top: clamp(8px, 1vh, 12px);
  display: grid;
  gap: clamp(6px, 0.9vh, 10px);
}

.hud-control-actions :deep(.cui-btn) {
  width: 100%;
  justify-content: center;
  text-transform: uppercase;
  letter-spacing: 0.2em;
  font-size: 0.65rem;
  padding: 10px 14px;
  border-radius: 10px;
  border: 1px solid rgba(180, 190, 200, 0.35);
  background: rgba(18, 22, 28, 0.8);
  color: rgba(220, 228, 236, 0.65);
  box-shadow: inset 0 0 12px rgba(160, 170, 180, 0.1);
  transition: all 0.2s ease;
}

.hud-control-actions :deep(.cui-btn:hover:not(:disabled)) {
  border-color: rgba(56, 244, 255, 0.65);
  color: var(--hud-cyan);
  box-shadow:
    0 0 14px rgba(56, 244, 255, 0.2),
    inset 0 0 16px rgba(56, 244, 255, 0.2);
  background: rgba(9, 18, 24, 0.95);
}

.hud-control-actions :deep(.hud-control-btn--stop:hover:not(:disabled)) {
  border-color: rgba(255, 155, 47, 0.75);
  color: var(--hud-amber);
  box-shadow:
    0 0 14px rgba(255, 155, 47, 0.25),
    inset 0 0 16px rgba(255, 155, 47, 0.2);
}

.hud-control-actions :deep(.hud-control-btn--status:hover:not(:disabled)) {
  border-color: rgba(56, 244, 255, 0.75);
  color: var(--hud-cyan);
}

.hud-clock {
  min-height: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  flex: 1;
}

.hud-clock-body {
  flex: 1;
  min-height: 0;
  margin-top: clamp(4px, 0.8vh, 8px);
}

.hud-clock-uptime {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin-top: clamp(4px, 0.8vh, 8px);
  padding: clamp(4px, 0.8vh, 8px) clamp(6px, 1vh, 10px);
  border-radius: 10px;
  border: 1px solid rgba(56, 244, 255, 0.25);
  background: rgba(8, 18, 26, 0.7);
}

.hud-clock-uptime-label {
  font-size: 0.65rem;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: var(--hud-muted);
  font-family: "Orbitron", "Rajdhani", sans-serif;
}

.hud-clock-uptime-value {
  font-size: 1.2rem;
  letter-spacing: 0.12em;
  font-family: "Orbitron", "Rajdhani", sans-serif;
  color: #ffffff;
}

@keyframes hud-wave-pulse {
  0%,
  100% {
    opacity: 0.45;
  }
  50% {
    opacity: 0.95;
  }
}

@media (max-width: 1200px) {
  .hud-grid {
    grid-template-columns: minmax(220px, 1fr) minmax(0, 2fr);
  }

  .hud-right {
    grid-column: 1 / -1;
    flex-direction: row;
  }

  .hud-control {
    min-height: auto;
  }
}

@media (max-width: 900px) {
  .hud-grid {
    grid-template-columns: 1fr;
  }

  .hud-vitals {
    grid-template-columns: 1fr;
  }

  .hud-vitals-rail {
    writing-mode: horizontal-tb;
    transform: none;
    text-align: left;
    margin-bottom: 8px;
  }

  .hud-center {
    grid-template-rows: auto;
  }

  .hud-right {
    flex-direction: column;
  }

  .hud-control--left {
    margin-top: 0;
  }
}

@media (max-width: 640px) {
  .hud-banner {
    flex-direction: column;
    align-items: flex-start;
  }

  .hud-banner-status {
    justify-content: flex-start;
  }
}
</style>
