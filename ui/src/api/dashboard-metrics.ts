import { get } from "./client";
import type { ApiError } from "./client";
import { endpoints } from "./endpoints";

/** Dashboard metrics served only by the Rust server; Python RCH 2.9.x answers 404. */

export type TrafficRange = "1h" | "24h" | "7d";

export const TRAFFIC_RANGES: readonly TrafficRange[] = ["1h", "24h", "7d"];

export interface TrafficCounts {
  received: number;
  sent: number;
  /** Subset of `sent` whose delivery failed. */
  failed: number;
}

export interface TrafficBucket extends TrafficCounts {
  startMs: number;
}

export interface MessageTraffic {
  range: TrafficRange;
  bucketSeconds: number;
  startMs: number;
  endMs: number;
  totals: TrafficCounts;
  buckets: TrafficBucket[];
}

export interface CpuHistory {
  intervalSeconds: number;
  capacity: number;
  /** Whole-machine CPU use, 0-100, oldest first. */
  samples: number[];
}

/** The endpoint is missing on this server, as opposed to failing. */
export const isUnsupportedMetric = (error: unknown): boolean => {
  const status = (error as ApiError | undefined)?.status;
  return status === 404 || status === 405 || status === 501;
};

const asRecord = (value: unknown): Record<string, unknown> => {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Expected a JSON object");
  }
  return value as Record<string, unknown>;
};

const count = (value: unknown, field: string): number => {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    throw new Error(`Invalid ${field} count`);
  }
  return value;
};

const decodeCounts = (value: unknown): TrafficCounts => {
  const record = asRecord(value);
  return {
    received: count(record.received, "received"),
    sent: count(record.sent, "sent"),
    failed: count(record.failed, "failed")
  };
};

export const decodeMessageTraffic = (payload: unknown): MessageTraffic => {
  const record = asRecord(payload);
  const range = TRAFFIC_RANGES.find((candidate) => candidate === record.range);
  if (!range) {
    throw new Error("Invalid traffic range");
  }
  if (!Array.isArray(record.buckets)) {
    throw new Error("Traffic buckets missing");
  }
  return {
    range,
    bucketSeconds: count(record.bucket_seconds, "bucket_seconds"),
    startMs: count(record.start_ts_ms, "start_ts_ms"),
    endMs: count(record.end_ts_ms, "end_ts_ms"),
    totals: decodeCounts(record.totals),
    buckets: record.buckets.map((bucket) => ({
      ...decodeCounts(bucket),
      startMs: count(asRecord(bucket).start_ts_ms, "start_ts_ms")
    }))
  };
};

export const decodeCpuHistory = (payload: unknown): CpuHistory => {
  const record = asRecord(payload);
  if (!Array.isArray(record.samples)) {
    throw new Error("CPU samples missing");
  }
  return {
    intervalSeconds: count(record.interval_seconds, "interval_seconds"),
    capacity: count(record.capacity, "capacity"),
    samples: record.samples.map((sample) => {
      const value = asRecord(sample).system_percent;
      if (typeof value !== "number" || !Number.isFinite(value)) {
        throw new Error("Invalid CPU sample");
      }
      return Math.min(100, Math.max(0, value));
    })
  };
};

export const fetchMessageTraffic = async (range: TrafficRange): Promise<MessageTraffic> =>
  decodeMessageTraffic(
    await get<unknown>(`${endpoints.chatTraffic}?range=${encodeURIComponent(range)}`, { retries: 0 })
  );

export const fetchCpuHistory = async (): Promise<CpuHistory> =>
  decodeCpuHistory(await get<unknown>(endpoints.statusCpu, { retries: 0 }));
