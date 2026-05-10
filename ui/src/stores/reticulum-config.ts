import { defineStore } from "pinia";
import { ref } from "vue";
import { endpoints } from "../api/endpoints";
import { get, post, put } from "../api/client";
import type { ApiError } from "../api/client";
import {
  createEmptyReticulumConfig,
  parseReticulumConfig,
  serializeReticulumConfig,
  type ReticulumConfigState
} from "../utils/reticulum-config";

export const useReticulumConfigStore = defineStore("reticulum-config", () => {
  const config = ref<ReticulumConfigState>(createEmptyReticulumConfig());
  const validation = ref<unknown>(null);
  const applyResult = ref<unknown>(null);
  const rollbackResult = ref<unknown>(null);
  const error = ref<string>("");
  const loading = ref(false);

  const loadConfig = async () => {
    loading.value = true;
    error.value = "";
    try {
      const text = await get<string>(endpoints.reticulumConfig);
      config.value = parseReticulumConfig(text);
    } finally {
      loading.value = false;
    }
  };

  const validateConfig = async () => {
    error.value = "";
    try {
      const payload = serializeReticulumConfig(config.value);
      validation.value = await post<unknown>(endpoints.reticulumConfigValidate, payload);
    } catch (err) {
      error.value = formatApiError(err);
      throw err;
    }
  };

  const applyConfig = async () => {
    error.value = "";
    try {
      const payload = serializeReticulumConfig(config.value);
      applyResult.value = await put<unknown>(endpoints.reticulumConfig, payload);
    } catch (err) {
      error.value = formatApiError(err);
      throw err;
    }
  };

  const rollbackConfig = async () => {
    error.value = "";
    try {
      rollbackResult.value = await post<unknown>(endpoints.reticulumConfigRollback);
    } catch (err) {
      error.value = formatApiError(err);
      throw err;
    }
  };

  return {
    config,
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
