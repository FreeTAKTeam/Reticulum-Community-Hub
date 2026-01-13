import { defineStore } from "pinia";
import { computed } from "vue";
import { ref } from "vue";
import { endpoints } from "../api/endpoints";
import { get } from "../api/client";
import type { TelemetryEntry } from "../api/types";
import { deriveMarkers } from "../utils/telemetry";
import type { TelemetryMarker } from "../utils/telemetry";

type TelemetryApiResponse = {
  entries?: TelemetryEntry[];
};

export const useTelemetryStore = defineStore("telemetry", () => {
  const entries = ref<TelemetryEntry[]>([]);
  const loading = ref(false);
  const topicId = ref<string>("");

  const markers = computed<TelemetryMarker[]>(() => deriveMarkers(entries.value));

  const fetchTelemetry = async (since: number) => {
    loading.value = true;
    const params = new URLSearchParams({ since: String(since) });
    if (topicId.value) {
      params.set("topic_id", topicId.value);
    }
    try {
      const response = await get<TelemetryApiResponse | TelemetryEntry[]>(
        `${endpoints.telemetry}?${params.toString()}`
      );
      entries.value = Array.isArray(response) ? response : response.entries ?? [];
    } finally {
      loading.value = false;
    }
  };

  const applySnapshot = (snapshot: TelemetryEntry[]) => {
    entries.value = snapshot;
  };

  const applyUpdate = (entry: TelemetryEntry) => {
    entries.value = [entry, ...entries.value.filter((item) => item.id !== entry.id)].slice(0, 200);
  };

  return {
    entries,
    loading,
    topicId,
    markers,
    fetchTelemetry,
    applySnapshot,
    applyUpdate
  };
});
