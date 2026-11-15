import type { TrafficBucket, TrafficRange } from "../../api/dashboard-metrics";

/** Presentation geometry for the dashboard CPU trace and message traffic chart. */

export const CPU_TRACE_WIDTH = 640;
export const CPU_TRACE_HEIGHT = 40;
const CPU_TRACE_PAD = 4;

export interface CpuTraceGeometry {
  line: string;
  area: string;
  head: { x: number; y: number } | null;
}

export const cpuTraceY = (percent: number): number => {
  const clamped = Math.min(100, Math.max(0, percent));
  return CPU_TRACE_HEIGHT - CPU_TRACE_PAD - (clamped / 100) * (CPU_TRACE_HEIGHT - CPU_TRACE_PAD * 2);
};

/**
 * Draw samples on a fixed 0-100% scale, newest at the right edge. A partially
 * filled history starts part-way across, so the time scale never stretches.
 */
export const buildCpuTrace = (samples: readonly number[], capacity: number): CpuTraceGeometry => {
  const slots = Math.max(2, capacity);
  const visible = samples.slice(-slots);
  if (visible.length === 0) {
    return { line: "", area: "", head: null };
  }
  const step = CPU_TRACE_WIDTH / (slots - 1);
  const offset = slots - visible.length;
  const points = visible.map((value, index) => ({
    x: (offset + index) * step,
    y: cpuTraceY(value)
  }));
  if (points.length === 1) {
    points.unshift({ x: Math.max(0, points[0].x - step), y: points[0].y });
  }
  const line = points
    .map((point, index) => `${index === 0 ? "M" : "L"}${point.x.toFixed(2)} ${point.y.toFixed(2)}`)
    .join(" ");
  const first = points[0];
  const last = points[points.length - 1];
  const area = `${line} L${last.x.toFixed(2)} ${CPU_TRACE_HEIGHT} L${first.x.toFixed(2)} ${CPU_TRACE_HEIGHT} Z`;
  return { line, area, head: last };
};

/** Gradient stop offsets (0 = top) where the stroke turns amber (70%) and red (90%). */
export const CPU_WARN_OFFSET = cpuTraceY(70) / CPU_TRACE_HEIGHT;
export const CPU_CRITICAL_OFFSET = cpuTraceY(90) / CPU_TRACE_HEIGHT;

/** Round the larger of received/sent up to a readable axis maximum. */
export const trafficAxisMax = (buckets: readonly TrafficBucket[]): number => {
  const peak = buckets.reduce((max, bucket) => Math.max(max, bucket.received, bucket.sent), 0);
  if (peak <= 4) {
    return 4;
  }
  const magnitude = 10 ** Math.floor(Math.log10(peak));
  const nice = [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]
    .map((factor) => factor * magnitude)
    .find((value) => peak <= value);
  return nice ?? 10 * magnitude;
};

export const trafficBarPercent = (value: number, axisMax: number): number =>
  axisMax > 0 ? Math.min(100, (value / axisMax) * 100) : 0;

export const TRAFFIC_BUCKET_LABEL: Record<TrafficRange, string> = {
  "1h": "/1m",
  "24h": "/15m",
  "7d": "/1h"
};

const formatClock = (ms: number, range: TrafficRange): string => {
  const date = new Date(ms);
  return range === "7d"
    ? date.toLocaleDateString([], { weekday: "short", day: "2-digit" })
    : date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
};

/** Five evenly spaced tick labels across the window, the last one reading "now". */
export const trafficTicks = (startMs: number, endMs: number, range: TrafficRange): string[] =>
  Array.from({ length: 5 }, (_, index) =>
    index === 4 ? "now" : formatClock(startMs + ((endMs - startMs) * index) / 4, range)
  );

export const trafficBucketLabel = (bucket: TrafficBucket, bucketSeconds: number, range: TrafficRange): string => {
  const end = bucket.startMs + bucketSeconds * 1000;
  return `${formatClock(bucket.startMs, range === "7d" ? "24h" : range)} – ${formatClock(end, range === "7d" ? "24h" : range)}`;
};
