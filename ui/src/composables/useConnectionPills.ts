import { computed } from "vue";

import { useConnectionStore } from "../stores/connection";

export const useConnectionPills = () => {
  const connectionStore = useConnectionStore();

  const baseUrl = computed(() => connectionStore.baseUrlDisplay);
  const connectionLabel = computed(() => connectionStore.statusLabel);
  const wsLabel = computed(() => connectionStore.wsLabel);

  const connectionClass = computed(() => {
    if (connectionStore.status === "online") {
      return "cui-status-success";
    }
    if (connectionStore.status === "offline") {
      return "cui-status-danger";
    }
    return "cui-status-accent";
  });

  const wsClass = computed(() => {
    if (connectionStore.wsLabel.toLowerCase() === "live") {
      return "cui-status-success";
    }
    return "cui-status-accent";
  });

  return {
    baseUrl,
    connectionLabel,
    wsLabel,
    connectionClass,
    wsClass
  };
};
