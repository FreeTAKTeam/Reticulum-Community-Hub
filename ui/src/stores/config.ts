import { defineStore } from "pinia";
import { ref } from "vue";
import { endpoints } from "../api/endpoints";
import { get } from "../api/client";
import { post } from "../api/client";
import type { ApiError } from "../api/client";
import { put } from "../api/client";

export const useConfigStore = defineStore("config", () => {
  const configText = ref("");
  const validation = ref<unknown>(null);
  const applyResult = ref<unknown>(null);
  const rollbackResult = ref<unknown>(null);
  const error = ref<string>("");
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
    error.value = "";
    try {
      validation.value = await post<unknown>(endpoints.configValidate, configText.value);
    } catch (err) {
      error.value = formatApiError(err);
      throw err;
    }
  };

  const applyConfig = async () => {
    error.value = "";
    try {
      applyResult.value = await put<unknown>(endpoints.config, configText.value);
    } catch (err) {
      error.value = formatApiError(err);
      throw err;
    }
  };

  const rollbackConfig = async () => {
    error.value = "";
    try {
      rollbackResult.value = await post<unknown>(endpoints.configRollback);
    } catch (err) {
      error.value = formatApiError(err);
      throw err;
    }
  };

  return {
    configText,
    validation,
    applyResult,
    rollbackResult,
    error,
    loading,
    loadConfig,
    validateConfig,
    applyConfig,
    rollbackConfig
  };
});

const formatApiError = (error: unknown) => {
  const apiError = error as ApiError;
  if (apiError?.body) {
    try {
      return typeof apiError.body === "string" ? apiError.body : JSON.stringify(apiError.body);
    } catch (err) {
      return String(apiError.body);
    }
  }
  return apiError?.message ?? "Request failed";
};
