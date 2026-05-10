import { defineStore } from "pinia";
import { computed } from "vue";
import { ref } from "vue";
import { endpoints } from "../api/endpoints";
import { get } from "../api/client";
import type { AppInfo } from "../api/types";

export const useAppStore = defineStore("app", () => {
  const appInfo = ref<AppInfo | null>(null);
  const loading = ref(false);
  const loaded = ref(false);

  const appName = computed(() => (appInfo.value?.name ?? "").trim());

  const fetchAppInfo = async (force = false) => {
    if (loading.value || (loaded.value && !force)) {
      return;
    }
    loading.value = true;
    try {
      appInfo.value = await get<AppInfo>(endpoints.appInfo);
      loaded.value = true;
    } finally {
      loading.value = false;
    }
  };

  return {
    appInfo,
    appName,
    loading,
    loaded,
    fetchAppInfo
  };
});
