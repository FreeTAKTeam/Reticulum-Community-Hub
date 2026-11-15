<template>
  <svg
    class="cpu-trace"
    :class="{ 'cpu-trace--unavailable': unavailable }"
    :viewBox="`0 0 ${CPU_TRACE_WIDTH} ${CPU_TRACE_HEIGHT}`"
    preserveAspectRatio="none"
    role="img"
    :aria-label="ariaLabel"
  >
    <defs>
      <linearGradient :id="strokeId" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="0" :y2="CPU_TRACE_HEIGHT">
        <stop offset="0" stop-color="var(--cpu-critical)" />
        <stop :offset="CPU_CRITICAL_OFFSET" stop-color="var(--cpu-critical)" />
        <stop :offset="CPU_CRITICAL_OFFSET" stop-color="var(--cpu-warn)" />
        <stop :offset="CPU_WARN_OFFSET" stop-color="var(--cpu-warn)" />
        <stop :offset="CPU_WARN_OFFSET" stop-color="var(--cpu-ok)" />
        <stop offset="1" stop-color="var(--cpu-ok)" />
      </linearGradient>
    </defs>
    <line
      class="cpu-trace-threshold"
      x1="0"
      :y1="warnY"
      :x2="CPU_TRACE_WIDTH"
      :y2="warnY"
      vector-effect="non-scaling-stroke"
    />
    <template v-if="unavailable">
      <line
        class="cpu-trace-baseline"
        x1="0"
        :y1="baselineY"
        :x2="CPU_TRACE_WIDTH"
        :y2="baselineY"
        vector-effect="non-scaling-stroke"
      />
    </template>
    <template v-else-if="geometry.line">
      <path class="cpu-trace-fill" :d="geometry.area" />
      <path class="cpu-trace-glow" :d="geometry.line" :stroke="`url(#${strokeId})`" vector-effect="non-scaling-stroke" />
      <path class="cpu-trace-line" :d="geometry.line" :stroke="`url(#${strokeId})`" vector-effect="non-scaling-stroke" />
    </template>
  </svg>
</template>

<script setup lang="ts">
import { computed, useId } from "vue";
import {
  CPU_CRITICAL_OFFSET,
  CPU_TRACE_HEIGHT,
  CPU_TRACE_WIDTH,
  CPU_WARN_OFFSET,
  buildCpuTrace,
  cpuTraceY
} from "./dashboard-charts";

const props = defineProps<{
  /** Whole-machine CPU percentages, oldest first; null when the server has none. */
  samples: readonly number[] | null;
  capacity: number;
}>();

const strokeId = `cpu-trace-stroke-${useId()}`;
const unavailable = computed(() => props.samples === null);
const geometry = computed(() => buildCpuTrace(props.samples ?? [], props.capacity));
const warnY = cpuTraceY(70);
const baselineY = cpuTraceY(0);

const ariaLabel = computed(() => {
  if (props.samples === null) {
    return "CPU load unavailable";
  }
  const latest = props.samples[props.samples.length - 1];
  return latest === undefined ? "CPU load: waiting for samples" : `CPU load ${Math.round(latest)} percent`;
});
</script>

<style scoped>
.cpu-trace {
  --cpu-ok: #38f4ff;
  --cpu-warn: #ff9b2f;
  --cpu-critical: #ff5d6e;
  position: relative;
  display: block;
  width: 100%;
  height: 100%;
}

.cpu-trace-threshold {
  stroke: rgba(255, 155, 47, 0.22);
  stroke-width: 1;
  stroke-dasharray: 3 4;
}

.cpu-trace-fill {
  fill: rgba(48, 231, 246, 0.22);
  filter: drop-shadow(0 0 10px rgba(48, 231, 246, 0.3));
}

.cpu-trace-glow {
  fill: none;
  stroke-width: 6;
  stroke-linecap: round;
  stroke-linejoin: round;
  opacity: 0.45;
  filter: blur(2px);
}

.cpu-trace-line {
  fill: none;
  stroke-width: 2.2;
  stroke-linecap: round;
  stroke-linejoin: round;
  filter: drop-shadow(0 0 4px rgba(56, 244, 255, 0.7));
}

.cpu-trace-baseline {
  stroke: rgba(231, 244, 255, 0.45);
  stroke-width: 1.5;
  stroke-dasharray: 4 5;
}

.cpu-trace--unavailable {
  opacity: 0.7;
}
</style>
