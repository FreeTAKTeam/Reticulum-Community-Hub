import { describe, expect, it } from "vitest";
import { createApp, h, nextTick } from "vue";
import type { Component } from "vue";
import {
  decodeCpuHistory,
  decodeMessageTraffic,
  isUnsupportedMetric
} from "../src/api/dashboard-metrics";
import type { MessageTraffic } from "../src/api/dashboard-metrics";
import CpuTrace from "../src/components/dashboard/CpuTrace.vue";
import MessageTrafficPanel from "../src/components/dashboard/MessageTrafficPanel.vue";
import {
  CPU_TRACE_HEIGHT,
  CPU_TRACE_WIDTH,
  buildCpuTrace,
  cpuTraceY,
  trafficAxisMax,
  trafficBarPercent
} from "../src/components/dashboard/dashboard-charts";

const mount = (component: Component, props: Record<string, unknown>) => {
  const host = document.createElement("div");
  const app = createApp({ render: () => h(component, props) });
  app.mount(host);
  return { host, unmount: () => app.unmount() };
};

const trafficPayload = {
  range: "1h",
  bucket_seconds: 60,
  start_ts_ms: 1_000_000,
  end_ts_ms: 1_120_000,
  totals: { received: 3, sent: 7, failed: 1 },
  buckets: [
    { start_ts_ms: 1_000_000, received: 3, sent: 0, failed: 0 },
    { start_ts_ms: 1_060_000, received: 0, sent: 7, failed: 1 }
  ]
};

describe("dashboard metrics decoding", () => {
  it("decodes message traffic histograms", () => {
    const traffic = decodeMessageTraffic(trafficPayload);
    expect(traffic.range).toBe("1h");
    expect(traffic.totals).toEqual({ received: 3, sent: 7, failed: 1 });
    expect(traffic.buckets[1]).toEqual({ startMs: 1_060_000, received: 0, sent: 7, failed: 1 });
  });

  it("rejects malformed traffic instead of drawing zeros", () => {
    expect(() => decodeMessageTraffic({ ...trafficPayload, range: "2h" })).toThrow();
    expect(() =>
      decodeMessageTraffic({ ...trafficPayload, buckets: [{ start_ts_ms: 1, received: "3", sent: 0, failed: 0 }] })
    ).toThrow();
  });

  it("decodes CPU samples and clamps them to 0-100", () => {
    const history = decodeCpuHistory({
      interval_seconds: 5,
      capacity: 120,
      samples: [
        { ts_ms: 1, system_percent: 12.5, process_percent: null },
        { ts_ms: 2, system_percent: 140, process_percent: 2 }
      ]
    });
    expect(history.samples).toEqual([12.5, 100]);
    expect(() => decodeCpuHistory({ interval_seconds: 5, capacity: 120, samples: [{ system_percent: "x" }] })).toThrow();
  });

  it("treats a missing endpoint as unsupported, not as a failure", () => {
    expect(isUnsupportedMetric({ status: 404 })).toBe(true);
    expect(isUnsupportedMetric({ status: 500 })).toBe(false);
    expect(isUnsupportedMetric(new Error("offline"))).toBe(false);
  });
});

describe("dashboard chart geometry", () => {
  it("draws CPU on a fixed scale anchored to the right edge", () => {
    expect(cpuTraceY(0)).toBeCloseTo(CPU_TRACE_HEIGHT - 4);
    expect(cpuTraceY(100)).toBeCloseTo(4);
    const trace = buildCpuTrace([50, 50], 5);
    expect(trace.head?.x).toBeCloseTo(CPU_TRACE_WIDTH);
    expect(trace.line.startsWith(`M${(CPU_TRACE_WIDTH * 3) / 4}`)).toBe(true);
    expect(buildCpuTrace([], 120).line).toBe("");
  });

  it("rounds the traffic axis up to a readable maximum", () => {
    const bucket = (received: number, sent: number) => ({ startMs: 0, received, sent, failed: 0 });
    expect(trafficAxisMax([])).toBe(4);
    expect(trafficAxisMax([bucket(3, 37)])).toBe(40);
    expect(trafficAxisMax([bucket(113, 2)])).toBe(150);
    expect(trafficBarPercent(20, 40)).toBe(50);
  });
});

describe("dashboard components", () => {
  it("renders received, sent and failed bars with totals", async () => {
    const traffic: MessageTraffic = decodeMessageTraffic(trafficPayload);
    const view = mount(MessageTrafficPanel, { traffic, range: "1h", state: "ready" });
    await nextTick();
    expect(view.host.querySelectorAll(".traffic-bar--in")).toHaveLength(2);
    expect(view.host.querySelectorAll(".traffic-bar-failed")).toHaveLength(1);
    expect(view.host.querySelector(".traffic-totals")?.textContent).toContain("7");
    expect(view.host.querySelector('[aria-pressed="true"]')?.textContent?.trim()).toBe("1H");
    view.unmount();
  });

  it("shows an explicit message when the server has no traffic endpoint", async () => {
    const view = mount(MessageTrafficPanel, { traffic: null, range: "24h", state: "unavailable" });
    await nextTick();
    expect(view.host.textContent).toContain("not reported by this server");
    expect(view.host.querySelector(".traffic-bar--in")).toBeNull();
    view.unmount();
  });

  it("draws a dashed baseline when CPU samples are unavailable", async () => {
    const view = mount(CpuTrace, { samples: null, capacity: 120 });
    await nextTick();
    expect(view.host.querySelector(".cpu-trace-baseline")).not.toBeNull();
    expect(view.host.querySelector(".cpu-trace-line")).toBeNull();
    expect(view.host.querySelector("svg")?.getAttribute("aria-label")).toBe("CPU load unavailable");
    view.unmount();
  });
});
