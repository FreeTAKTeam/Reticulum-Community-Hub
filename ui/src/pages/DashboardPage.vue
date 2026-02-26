<template>
  <div class="dashboard-hud">
    <section class="hud-banner">
      <div class="hud-brand">
        <div class="hud-brand-mark">
          <span class="hud-brand-symbol">RCH</span>
          <span class="hud-brand-subtitle">Reticulum Community Hub</span>
        </div>
        <div class="hud-brand-trace" aria-hidden="true">
          <svg class="hud-brand-trace-svg" viewBox="0 0 640 40" preserveAspectRatio="none">
            <path class="hud-brand-trace-fill" :d="brandTraceAreaPath" />
            <path class="hud-brand-trace-carrier-glow" :d="brandTracePath" />
            <path class="hud-brand-trace-carrier" :d="brandTracePath" />
            <path class="hud-brand-trace-fringe" :d="brandTracePath" />
            <path class="hud-brand-trace-pulse" :d="brandTracePath" />
          </svg>
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
import OnlineHelpLauncher from "../components/OnlineHelpLauncher.vue";
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
let sparklineTickId: number | undefined;
let brandTraceFrameId: number | undefined;
let brandTraceLastFrameAt = 0;
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
  const base = event.id ?? event.created_at ?? "event";
  const category = event.category ?? "unknown";
  const createdAt = event.created_at ?? "no-time";
  return `${base}-${category}-${createdAt}-${index}`;
};

const isEventExpanded = (key: string) => Boolean(expandedEvents.value[key]);

const toggleEventDetails = (key: string) => {
  expandedEvents.value[key] = !expandedEvents.value[key];
};

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

interface BrandTraceState {
  values: number[];
  travel: number;
  incoming: number;
  speed: number;
}

const BRAND_TRACE_WIDTH = 640;
const BRAND_TRACE_HEIGHT = 40;
const BRAND_TRACE_POINT_COUNT = 180;
const BRAND_TRACE_POINT_STEP_X = BRAND_TRACE_WIDTH / (BRAND_TRACE_POINT_COUNT - 1);
const BRAND_TRACE_ANCHOR_Y = 19.5;
const BRAND_TRACE_AMPLITUDE = 14.2;
const BRAND_TRACE_MIN = 0.04;
const BRAND_TRACE_MAX = 0.96;
const BRAND_TRACE_MAX_DELTA_SECONDS = 0.065;
const BRAND_TRACE_SPEED_SLOWDOWN_FACTOR = 0.27;

const brandTracePath = ref("");
const brandTraceAreaPath = ref("");

const clampBrandTrace = (value: number) => Math.max(BRAND_TRACE_MIN, Math.min(BRAND_TRACE_MAX, value));

const randomBrandTraceSpeed = () => (10 + Math.random() * 8) * BRAND_TRACE_SPEED_SLOWDOWN_FACTOR;

const randomBrandTracePoint = (previous: number) => {
  const drift = (Math.random() - 0.5) * 0.34;
  const recoil = (0.5 - previous) * (0.08 + Math.random() * 0.1);
  const spike = Math.random() < 0.18 ? (Math.random() - 0.5) * (0.72 + Math.random() * 0.36) : 0;
  const micro = (Math.random() - 0.5) * 0.08;
  return clampBrandTrace(previous + drift + recoil + spike + micro);
};

const createBrandTraceSeed = () => {
  let current = clampBrandTrace(0.5 + (Math.random() - 0.5) * 0.18);
  return Array.from({ length: BRAND_TRACE_POINT_COUNT }, () => {
    current = randomBrandTracePoint(current);
    return current;
  });
};

const createBrandTraceState = (): BrandTraceState => {
  const values = createBrandTraceSeed();
  const lastValue = values[values.length - 1] ?? 0.5;
  return {
    values,
    travel: 0,
    incoming: randomBrandTracePoint(lastValue),
    speed: randomBrandTraceSpeed()
  };
};

const brandTraceState = createBrandTraceState();

const toBrandTraceY = (value: number) => {
  const y = BRAND_TRACE_ANCHOR_Y - (value - 0.5) * BRAND_TRACE_AMPLITUDE * 2;
  return Math.max(2, Math.min(BRAND_TRACE_HEIGHT - 2, y));
};

const sampleBrandTraceValue = (state: BrandTraceState, index: number) => {
  const position = index + state.travel;
  const baseIndex = Math.floor(position);
  const blend = position - baseIndex;
  const current = baseIndex < state.values.length ? state.values[baseIndex] : state.incoming;
  const next = baseIndex + 1 < state.values.length ? state.values[baseIndex + 1] : state.incoming;
  return current + (next - current) * blend;
};

const renderBrandTrace = () => {
  const firstY = toBrandTraceY(sampleBrandTraceValue(brandTraceState, 0)).toFixed(2);
  let path = `M0.00 ${firstY}`;
  for (let index = 1; index < BRAND_TRACE_POINT_COUNT; index += 1) {
    const x = (index * BRAND_TRACE_POINT_STEP_X).toFixed(2);
    const y = toBrandTraceY(sampleBrandTraceValue(brandTraceState, index)).toFixed(2);
    path += ` L${x} ${y}`;
  }
  brandTracePath.value = path;
  brandTraceAreaPath.value = `${path} L${BRAND_TRACE_WIDTH.toFixed(2)} ${BRAND_TRACE_HEIGHT.toFixed(2)} L0.00 ${BRAND_TRACE_HEIGHT.toFixed(2)} Z`;
};

const advanceBrandTrace = (deltaSeconds: number) => {
  brandTraceState.travel += deltaSeconds * brandTraceState.speed;
  while (brandTraceState.travel >= 1) {
    brandTraceState.travel -= 1;
    brandTraceState.values.shift();
    brandTraceState.values.push(brandTraceState.incoming);
    const lastValue = brandTraceState.values[brandTraceState.values.length - 1] ?? 0.5;
    brandTraceState.incoming = randomBrandTracePoint(lastValue);
    if (Math.random() < 0.1) {
      brandTraceState.speed = randomBrandTraceSpeed();
    }
  }
};

const animateBrandTrace = (timestamp: number) => {
  const deltaSeconds = Math.min((timestamp - brandTraceLastFrameAt) / 1000, BRAND_TRACE_MAX_DELTA_SECONDS);
  brandTraceLastFrameAt = timestamp;
  advanceBrandTrace(deltaSeconds);
  renderBrandTrace();
  brandTraceFrameId = window.requestAnimationFrame(animateBrandTrace);
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

  renderBrandTrace();
  if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    brandTraceLastFrameAt = window.performance.now();
    brandTraceFrameId = window.requestAnimationFrame(animateBrandTrace);
  }

  pollerId = window.setInterval(() => {
    dashboard.refresh();
  }, 30000);

  sparklineTickId = window.setInterval(() => {
    refreshSparklines();
  }, SPARKLINE_TICK_MS);

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
  if (sparklineTickId) {
    window.clearInterval(sparklineTickId);
  }
  if (brandTraceFrameId) {
    window.cancelAnimationFrame(brandTraceFrameId);
  }
  brandTraceFrameId = undefined;
  brandTraceLastFrameAt = 0;
});
</script>

<style scoped src="./styles/DashboardPage.css"></style>


