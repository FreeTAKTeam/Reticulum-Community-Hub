import { defineStore } from "pinia";
import { ref } from "vue";
import { endpoints } from "../api/endpoints";
import { get } from "../api/client";
import type { EventEntry } from "../api/types";
import type { StatusResponse } from "../api/types";
import { useConnectionStore } from "./connection";

type StatusApiPayload = StatusResponse & {
  uptime_seconds?: number;
};

type EventApiPayload = {
  timestamp?: string;
  type?: string;
  message?: string;
  metadata?: Record<string, unknown>;
};

const normalizeStatus = (payload: StatusApiPayload): StatusResponse => {
  const uptime = payload.uptime ?? payload.uptime_seconds;
  const telemetry = payload.telemetry
    ? {
        ...payload.telemetry,
        total: payload.telemetry.total ?? payload.telemetry.ingest_count
      }
    : undefined;
  return {
    ...payload,
    uptime,
    telemetry
  };
};

const normalizeEvent = (payload: EventApiPayload): EventEntry => ({
  id: payload.timestamp ?? `${Date.now()}`,
  created_at: payload.timestamp,
  message: payload.message,
  level: "info",
  category: payload.type,
  metadata: payload.metadata ?? {}
});

export const useDashboardStore = defineStore("dashboard", () => {
  const status = ref<StatusResponse | null>(null);
  const events = ref<EventEntry[]>([]);
  const loading = ref(false);

  const refresh = async () => {
    loading.value = true;
    const connectionStore = useConnectionStore();
    try {
      const response = await get<StatusApiPayload>(endpoints.status);
      status.value = normalizeStatus(response);
      const eventResponse = await get<EventApiPayload[]>(endpoints.events);
      events.value = eventResponse.map(normalizeEvent);
      connectionStore.setOnline();
    } finally {
      loading.value = false;
    }
  };

  const pushEvent = (event: EventApiPayload | EventEntry) => {
    const mapped = "timestamp" in event || "type" in event ? normalizeEvent(event as EventApiPayload) : (event as EventEntry);
    events.value = [mapped, ...events.value].slice(0, 50);
  };

  const updateStatus = (payload: StatusApiPayload) => {
    status.value = normalizeStatus(payload);
  };

  return {
    status,
    events,
    loading,
    refresh,
    pushEvent,
    updateStatus
  };
});
