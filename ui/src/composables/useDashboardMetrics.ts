import { onScopeDispose, ref, watch } from "vue";
import {
  fetchCpuHistory,
  fetchMessageTraffic,
  isUnsupportedMetric
} from "../api/dashboard-metrics";
import type { MessageTraffic, TrafficRange } from "../api/dashboard-metrics";
import { useConnectionStore } from "../stores/connection";

export type MetricState = "loading" | "ready" | "unavailable" | "error";

const DEFAULT_CPU_CAPACITY = 120;
const DEFAULT_CPU_POLL_MS = 5_000;
const TRAFFIC_POLL_MS = 30_000;

const isAbort = (error: unknown) => error instanceof DOMException && error.name === "AbortError";

/**
 * Polls the server-owned CPU history and message traffic for the dashboard.
 * Servers without these endpoints (Python RCH 2.9.x) are reported as unavailable.
 */
export const useDashboardMetrics = () => {
  const connection = useConnectionStore();

  /** null once the server is known not to report CPU samples. */
  const cpuSamples = ref<number[] | null>([]);
  const cpuCapacity = ref(DEFAULT_CPU_CAPACITY);
  const trafficRange = ref<TrafficRange>("24h");
  const traffic = ref<MessageTraffic | null>(null);
  const trafficState = ref<MetricState>("loading");

  let running = false;
  let cpuTimer: number | undefined;
  let trafficTimer: number | undefined;
  let cpuPollMs = DEFAULT_CPU_POLL_MS;
  let cpuInFlight = false;
  let trafficRequest = 0;

  const clearCpuTimer = () => {
    if (cpuTimer !== undefined) {
      window.clearInterval(cpuTimer);
      cpuTimer = undefined;
    }
  };

  const clearTrafficTimer = () => {
    if (trafficTimer !== undefined) {
      window.clearInterval(trafficTimer);
      trafficTimer = undefined;
    }
  };

  const pollCpu = async () => {
    if (!running || cpuInFlight || cpuSamples.value === null) {
      return;
    }
    cpuInFlight = true;
    try {
      const history = await fetchCpuHistory();
      if (!running) {
        return;
      }
      cpuSamples.value = history.samples;
      cpuCapacity.value = history.capacity || DEFAULT_CPU_CAPACITY;
      const intervalMs = history.intervalSeconds > 0 ? history.intervalSeconds * 1000 : DEFAULT_CPU_POLL_MS;
      if (intervalMs !== cpuPollMs) {
        cpuPollMs = intervalMs;
        clearCpuTimer();
        cpuTimer = window.setInterval(() => void pollCpu(), cpuPollMs);
      }
    } catch (error) {
      if (!running || isAbort(error)) {
        return;
      }
      if (isUnsupportedMetric(error)) {
        cpuSamples.value = null;
        clearCpuTimer();
        return;
      }
      console.warn("Unable to load CPU samples", error);
    } finally {
      cpuInFlight = false;
    }
  };

  const pollTraffic = async () => {
    if (!running || trafficState.value === "unavailable") {
      return;
    }
    const request = ++trafficRequest;
    const range = trafficRange.value;
    try {
      const result = await fetchMessageTraffic(range);
      if (!running || request !== trafficRequest) {
        return;
      }
      traffic.value = result;
      trafficState.value = "ready";
    } catch (error) {
      if (!running || request !== trafficRequest || isAbort(error)) {
        return;
      }
      if (isUnsupportedMetric(error)) {
        trafficState.value = "unavailable";
        traffic.value = null;
        clearTrafficTimer();
        return;
      }
      console.warn("Unable to load message traffic", error);
      if (!traffic.value) {
        trafficState.value = "error";
      }
    }
  };

  const start = () => {
    if (running) {
      return;
    }
    running = true;
    void pollCpu();
    void pollTraffic();
    cpuTimer = window.setInterval(() => void pollCpu(), cpuPollMs);
    trafficTimer = window.setInterval(() => void pollTraffic(), TRAFFIC_POLL_MS);
  };

  const stop = () => {
    running = false;
    trafficRequest += 1;
    clearCpuTimer();
    clearTrafficTimer();
  };

  const reset = () => {
    stop();
    cpuSamples.value = [];
    cpuCapacity.value = DEFAULT_CPU_CAPACITY;
    cpuPollMs = DEFAULT_CPU_POLL_MS;
    traffic.value = null;
    trafficState.value = "loading";
  };

  watch(trafficRange, () => {
    if (!running || trafficState.value === "unavailable") {
      return;
    }
    traffic.value = null;
    trafficState.value = "loading";
    void pollTraffic();
  });

  watch(
    () => connection.requestIdentity,
    () => {
      if (running) {
        reset();
        start();
      }
    }
  );

  onScopeDispose(stop);

  return { cpuSamples, cpuCapacity, trafficRange, traffic, trafficState, start, stop };
};
