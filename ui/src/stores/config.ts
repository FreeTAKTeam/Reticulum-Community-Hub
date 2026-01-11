import { defineStore } from "pinia";
import { ref } from "vue";
import { endpoints } from "../api/endpoints";
import { get } from "../api/client";
import { post } from "../api/client";
import { put } from "../api/client";

export const useConfigStore = defineStore("config", () => {
  const configText = ref("");
  const validation = ref<unknown>(null);
  const applyResult = ref<unknown>(null);
  const rollbackResult = ref<unknown>(null);
  const loading = ref(false);

  const loadConfig = async () => {
    loading.value = true;
    try {
      configText.value = await get<string>(endpoints.config);
    } finally {
      loading.value = false;
    }
  };

  const validateConfig = async () => {
    validation.value = await post<unknown>(endpoints.configValidate, { config: configText.value });
  };

  const applyConfig = async () => {
    applyResult.value = await put<unknown>(endpoints.config, { config: configText.value });
  };

  const rollbackConfig = async () => {
    rollbackResult.value = await post<unknown>(endpoints.configRollback);
  };

  return {
    configText,
    validation,
    applyResult,
    rollbackResult,
    loading,
    loadConfig,
    validateConfig,
    applyConfig,
    rollbackConfig
  };
});
