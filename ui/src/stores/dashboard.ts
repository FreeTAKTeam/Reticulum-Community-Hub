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
      events.value = await get<EventEntry[]>(endpoints.events);
      connectionStore.setOnline();
    } finally {
      loading.value = false;
    }
  };

  const pushEvent = (event: EventEntry) => {
    events.value = [event, ...events.value].slice(0, 50);
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
