<template>
  <section class="traffic" aria-labelledby="traffic-title">
    <header class="traffic-header">
      <div class="traffic-heading">
        <h2 id="traffic-title" class="traffic-title">Message Traffic</h2>
        <span class="traffic-subtitle">Received &amp; Sent</span>
      </div>
      <div class="traffic-range" role="group" aria-label="Time range">
        <button
          v-for="option in TRAFFIC_RANGES"
          :key="option"
          type="button"
          class="traffic-range-button"
          :class="{ 'traffic-range-button--active': option === range }"
          :aria-pressed="option === range"
          @click="emit('update:range', option)"
        >
          {{ option.toUpperCase() }}
        </button>
      </div>
    </header>

    <div class="traffic-totals">
      <div v-for="total in totals" :key="total.key" class="traffic-total">
        <span class="traffic-total-label" :class="`traffic-total-label--${total.key}`">
          <span class="traffic-swatch" :class="`traffic-swatch--${total.key}`" aria-hidden="true" />
          {{ total.label }}
        </span>
        <span class="traffic-total-value">{{ total.value }}</span>
      </div>
    </div>

    <div class="traffic-chart">
      <div v-if="!hasTraffic || !traffic" class="traffic-empty" role="status">
        <span class="traffic-empty-line" aria-hidden="true" />
        <span class="traffic-empty-message">{{ emptyMessage }}</span>
      </div>
      <template v-else>
        <div class="traffic-axis-y" aria-hidden="true">
          <div class="traffic-axis-half">
            <span>{{ axisLabel(axisMax) }}</span><span>{{ axisLabel(axisMax / 2) }}</span><span class="traffic-in">IN</span>
          </div>
          <div class="traffic-axis-half">
            <span class="traffic-out">OUT</span><span>{{ axisLabel(axisMax / 2) }}</span><span>{{ axisLabel(axisMax) }}</span>
          </div>
          <span class="traffic-axis-unit">{{ TRAFFIC_BUCKET_LABEL[traffic.range] }}</span>
        </div>
        <div class="traffic-plot-column">
          <div
            class="traffic-plot"
            role="img"
            :aria-label="plotLabel"
            :style="{ '--bucket-count': traffic.buckets.length }"
            @mouseleave="hovered = null"
          >
            <span class="traffic-grid traffic-grid--top" aria-hidden="true" />
            <span class="traffic-grid traffic-grid--upper" aria-hidden="true" />
            <span class="traffic-grid traffic-grid--lower" aria-hidden="true" />
            <span class="traffic-grid traffic-grid--bottom" aria-hidden="true" />
            <div class="traffic-row traffic-row--in">
              <span
                v-for="(bucket, index) in traffic.buckets"
                :key="`in-${bucket.startMs}`"
                class="traffic-slot"
                :class="{ 'traffic-slot--dim': hovered !== null && hovered !== index }"
                @mouseenter="hovered = index"
              >
                <span class="traffic-bar traffic-bar--in" :style="{ height: `${percent(bucket.received)}%` }" />
              </span>
            </div>
            <span class="traffic-zero" aria-hidden="true" />
            <div class="traffic-row traffic-row--out">
              <span
                v-for="(bucket, index) in traffic.buckets"
                :key="`out-${bucket.startMs}`"
                class="traffic-slot"
                :class="{ 'traffic-slot--dim': hovered !== null && hovered !== index }"
                @mouseenter="hovered = index"
              >
                <span class="traffic-bar traffic-bar--out" :style="{ height: `${percent(bucket.sent)}%` }">
                  <span
                    v-if="bucket.failed > 0"
                    class="traffic-bar-failed"
                    :style="{ height: `${failedShare(bucket)}%` }"
                  />
                </span>
              </span>
            </div>
            <template v-if="hoveredBucket">
              <span class="traffic-cursor" :style="{ left: `${hoverLeft}%` }" aria-hidden="true" />
              <div
                class="traffic-tooltip"
                :class="{ 'traffic-tooltip--left': hoverLeft > 50 }"
                :style="{ left: `${hoverLeft}%` }"
              >
                <span class="traffic-tooltip-range">{{ hoveredRange }}</span>
                <span class="traffic-tooltip-row"><span class="traffic-in">Received</span><strong>{{ formatNumber(hoveredBucket.received) }}</strong></span>
                <span class="traffic-tooltip-row"><span class="traffic-out">Sent</span><strong>{{ formatNumber(hoveredBucket.sent) }}</strong></span>
                <span class="traffic-tooltip-row"><span class="traffic-failed">Failed</span><strong>{{ formatNumber(hoveredBucket.failed) }}</strong></span>
              </div>
            </template>
          </div>
          <div class="traffic-axis-x" aria-hidden="true">
            <span v-for="(tick, index) in ticks" :key="`tick-${index}`">{{ tick }}</span>
          </div>
        </div>
      </template>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { TRAFFIC_RANGES } from "../../api/dashboard-metrics";
import type { MessageTraffic, TrafficBucket, TrafficRange } from "../../api/dashboard-metrics";
import { formatNumber } from "../../utils/format";
import {
  TRAFFIC_BUCKET_LABEL,
  trafficAxisMax,
  trafficBarPercent,
  trafficBucketLabel,
  trafficTicks
} from "./dashboard-charts";

export type TrafficPanelState = "loading" | "ready" | "unavailable" | "error";

const props = defineProps<{
  traffic: MessageTraffic | null;
  range: TrafficRange;
  state: TrafficPanelState;
}>();

const emit = defineEmits<{ "update:range": [range: TrafficRange] }>();

const hovered = ref<number | null>(null);
watch(() => props.traffic, () => {
  if (hovered.value !== null && hovered.value >= (props.traffic?.buckets.length ?? 0)) {
    hovered.value = null;
  }
});

const RANGE_TEXT: Record<TrafficRange, string> = { "1h": "hour", "24h": "24 hours", "7d": "7 days" };

const hasTraffic = computed(() => {
  const counts = props.traffic?.totals;
  return props.state === "ready" && Boolean(counts) && (counts?.received ?? 0) + (counts?.sent ?? 0) > 0;
});

const axisMax = computed(() => trafficAxisMax(props.traffic?.buckets ?? []));
const percent = (value: number) => trafficBarPercent(value, axisMax.value);
const failedShare = (bucket: TrafficBucket) =>
  bucket.sent > 0 ? Math.max(8, Math.min(100, (bucket.failed / bucket.sent) * 100)) : 0;
const axisLabel = (value: number) => (Number.isInteger(value) ? String(value) : value.toFixed(1));

const totals = computed(() => {
  const counts = props.state === "ready" ? props.traffic?.totals : undefined;
  const show = (value: number | undefined) => (value === undefined ? "–" : formatNumber(value));
  return [
    { key: "in", label: "Received", value: show(counts?.received) },
    { key: "out", label: "Sent", value: show(counts?.sent) },
    { key: "failed", label: "Failed", value: show(counts?.failed) }
  ];
});

const emptyMessage = computed(() => {
  switch (props.state) {
    case "loading":
      return "Loading message traffic…";
    case "unavailable":
      return "Message traffic is not reported by this server";
    case "error":
      return "Message traffic could not be loaded";
    default:
      return `No messages in the last ${RANGE_TEXT[props.range]}`;
  }
});

const ticks = computed(() =>
  props.traffic ? trafficTicks(props.traffic.startMs, props.traffic.endMs, props.traffic.range) : []
);

const hoveredBucket = computed(() =>
  hovered.value === null ? null : props.traffic?.buckets[hovered.value] ?? null
);
const hoverLeft = computed(() => {
  const count = props.traffic?.buckets.length ?? 0;
  return hovered.value === null || count === 0 ? 0 : ((hovered.value + 0.5) / count) * 100;
});
const hoveredRange = computed(() =>
  hoveredBucket.value && props.traffic
    ? trafficBucketLabel(hoveredBucket.value, props.traffic.bucketSeconds, props.traffic.range)
    : ""
);

const plotLabel = computed(() => {
  const counts = props.traffic?.totals;
  return counts
    ? `Last ${RANGE_TEXT[props.range]}: ${counts.received} received, ${counts.sent} sent, ${counts.failed} failed`
    : "Message traffic";
});
</script>

<style scoped>
.traffic {
  display: flex;
  flex-direction: column;
  gap: clamp(8px, 1.2vh, 14px);
  min-height: 0;
  height: 100%;
}

.traffic-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.traffic-heading {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.traffic-title {
  margin: 0;
  font-family: "Orbitron", "Rajdhani", sans-serif;
  font-size: 16px;
  font-weight: 600;
  letter-spacing: 3px;
  text-transform: uppercase;
  color: var(--hud-text);
}

.traffic-subtitle {
  font-size: 14px;
  color: var(--hud-muted);
}

.traffic-range {
  display: flex;
  gap: 2px;
  padding: 3px;
  border: 1px solid rgba(56, 244, 255, 0.3);
  border-radius: 999px;
}

.traffic-range-button {
  min-height: 28px;
  padding: 4px 12px;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: var(--hud-muted);
  font-family: "Orbitron", "Rajdhani", sans-serif;
  font-size: 10px;
  letter-spacing: 2px;
  cursor: pointer;
}

.traffic-range-button:hover {
  color: var(--hud-text);
}

.traffic-range-button:focus-visible {
  outline: 2px solid var(--hud-cyan);
  outline-offset: 1px;
}

.traffic-range-button--active {
  background: rgba(56, 244, 255, 0.16);
  color: var(--hud-cyan);
}

.traffic-totals {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 36px;
}

.traffic-total {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.traffic-total-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-family: "Orbitron", "Rajdhani", sans-serif;
  font-size: 10px;
  letter-spacing: 2px;
  text-transform: uppercase;
}

.traffic-total-label--in,
.traffic-in {
  color: var(--hud-cyan);
}

.traffic-total-label--out,
.traffic-out {
  color: var(--hud-amber);
}

.traffic-total-label--failed,
.traffic-failed {
  color: #ff7d8a;
}

.traffic-swatch {
  width: 14px;
  height: 6px;
  border-radius: 3px;
}

.traffic-swatch--in {
  background: var(--hud-cyan);
}

.traffic-swatch--out {
  background: var(--hud-amber);
}

.traffic-swatch--failed {
  background: var(--hud-red);
}

.traffic-total-value {
  font-family: "Orbitron", "Rajdhani", sans-serif;
  font-size: clamp(20px, 2.6vh, 28px);
  font-weight: 500;
  color: var(--hud-text);
}

.traffic-chart {
  position: relative;
  flex: 1;
  min-height: 170px;
  display: flex;
  gap: 10px;
  padding: 12px 14px 8px 8px;
  border: 1px solid rgba(56, 244, 255, 0.2);
  border-radius: 12px;
  background: linear-gradient(180deg, rgba(6, 24, 32, 0.85), rgba(6, 12, 18, 0.95));
  box-shadow: inset 0 0 20px rgba(4, 18, 24, 0.8);
}

.traffic-axis-y {
  width: 38px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 11px;
  color: var(--hud-muted);
  text-align: right;
}

.traffic-axis-half {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.traffic-axis-unit {
  margin-top: 6px;
  line-height: 14px;
}

.traffic-plot-column {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.traffic-plot {
  position: relative;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.traffic-grid {
  position: absolute;
  left: 0;
  right: 0;
  height: 1px;
  background: rgba(56, 244, 255, 0.08);
  pointer-events: none;
}

.traffic-grid--top {
  top: 0;
}

.traffic-grid--upper {
  top: 25%;
}

.traffic-grid--lower {
  top: 75%;
}

.traffic-grid--bottom {
  bottom: 0;
}

.traffic-row {
  flex: 1;
  display: grid;
  grid-template-columns: repeat(var(--bucket-count), minmax(0, 1fr));
  gap: 2px;
}

.traffic-slot {
  display: flex;
  height: 100%;
  transition: opacity 120ms ease;
}

.traffic-row--in .traffic-slot {
  align-items: flex-end;
}

.traffic-row--out .traffic-slot {
  align-items: flex-start;
}

.traffic-slot--dim {
  opacity: 0.55;
}

.traffic-bar {
  width: 100%;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  overflow: hidden;
}

.traffic-bar--in {
  border-radius: 2px 2px 0 0;
  background: linear-gradient(180deg, #8ffaff, var(--hud-cyan) 40%, rgba(56, 244, 255, 0.55));
  box-shadow: 0 0 6px rgba(56, 244, 255, 0.35);
}

.traffic-bar--out {
  border-radius: 0 0 2px 2px;
  background: linear-gradient(0deg, #ffc27a, var(--hud-amber) 40%, rgba(255, 155, 47, 0.55));
  box-shadow: 0 0 6px rgba(255, 155, 47, 0.3);
}

.traffic-bar-failed {
  width: 100%;
  min-height: 2px;
  background: var(--hud-red);
}

.traffic-zero {
  height: 1px;
  background: rgba(231, 244, 255, 0.45);
}

.traffic-cursor {
  position: absolute;
  top: -4px;
  bottom: -4px;
  width: 1px;
  background: rgba(231, 244, 255, 0.7);
  pointer-events: none;
}

.traffic-tooltip {
  position: absolute;
  top: 4px;
  width: 180px;
  margin-left: 12px;
  padding: 8px 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  border: 1px solid rgba(56, 244, 255, 0.55);
  border-radius: 10px;
  background: rgba(4, 14, 20, 0.96);
  box-shadow: 0 0 18px rgba(56, 244, 255, 0.2);
  font-size: 14px;
  color: var(--hud-text);
  pointer-events: none;
  z-index: 2;
}

.traffic-tooltip--left {
  margin-left: -192px;
}

.traffic-tooltip-range {
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 11px;
  color: var(--hud-muted);
}

.traffic-tooltip-row {
  display: flex;
  justify-content: space-between;
}

.traffic-axis-x {
  margin-top: 6px;
  display: flex;
  justify-content: space-between;
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 11px;
  color: var(--hud-muted);
}

.traffic-empty {
  position: relative;
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.traffic-empty-line {
  position: absolute;
  left: 0;
  right: 0;
  top: 50%;
  height: 1px;
  background: rgba(231, 244, 255, 0.35);
}

.traffic-empty-message {
  position: relative;
  padding: 6px 14px;
  border: 1px solid rgba(56, 244, 255, 0.3);
  border-radius: 999px;
  background: rgba(4, 14, 20, 0.96);
  font-size: 14px;
  color: rgba(231, 244, 255, 0.75);
}

@media (prefers-reduced-motion: reduce) {
  .traffic-slot {
    transition: none;
  }
}
</style>
