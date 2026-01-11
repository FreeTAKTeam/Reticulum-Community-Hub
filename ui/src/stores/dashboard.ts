import { defineStore } from "pinia";
import { ref } from "vue";
import { endpoints } from "../api/endpoints";
import { get } from "../api/client";
import type { EventEntry } from "../api/types";
import type { StatusResponse } from "../api/types";
import { useConnectionStore } from "./connection";

export const useDashboardStore = defineStore("dashboard", () => {
  const status = ref<StatusResponse | null>(null);
  const events = ref<EventEntry[]>([]);
  const loading = ref(false);

  const refresh = async () => {
    loading.value = true;
    const connectionStore = useConnectionStore();
    try {
      status.value = await get<StatusResponse>(endpoints.status);
      events.value = await get<EventEntry[]>(endpoints.events);
      connectionStore.setOnline();
    } finally {
      loading.value = false;
    }
  };

  const pushEvent = (event: EventEntry) => {
    events.value = [event, ...events.value].slice(0, 50);
  };

  const updateStatus = (payload: StatusResponse) => {
    status.value = payload;
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
