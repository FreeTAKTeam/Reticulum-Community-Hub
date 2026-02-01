import { computed } from "vue";
import { ref } from "vue";
import { defineStore } from "pinia";
import { loadJson } from "../utils/storage";
import { saveJson } from "../utils/storage";

export type AuthMode = "none" | "bearer" | "apiKey" | "both";
export type ConnectionStatus = "online" | "offline" | "unknown";
export type AuthStatus = "ok" | "unauthenticated" | "forbidden" | "unknown";

interface ConnectionState {
  baseUrl: string;
  wsBaseUrl?: string;
  authMode: AuthMode;
  token: string;
  apiKey: string;
}

const STORAGE_KEY = "rth-ui-connection";
const DEFAULT_LOCAL_HTTP = "http://127.0.0.1:8000";
const DEFAULT_LOCAL_WS = "ws://127.0.0.1:8000";

const isFileOrigin = (): boolean => {
  if (typeof window === "undefined") {
    return false;
  }
  return window.location.protocol === "file:" || window.location.origin === "null";
};

const resolveDefaultBaseUrl = (): string => {
  const envBaseUrl = import.meta.env.VITE_RTH_BASE_URL;
  if (envBaseUrl) {
    return envBaseUrl;
  }
  if (isFileOrigin()) {
    return DEFAULT_LOCAL_HTTP;
  }
  return "";
};

const resolveDefaultWsBaseUrl = (): string => {
  const envWsBaseUrl = import.meta.env.VITE_RTH_WS_BASE_URL;
  if (envWsBaseUrl) {
    return envWsBaseUrl;
  }
  if (isFileOrigin()) {
    return DEFAULT_LOCAL_WS;
  }
  return "";
};

export const useConnectionStore = defineStore("connection", () => {
  const stored = loadJson<ConnectionState>(STORAGE_KEY, {
    baseUrl: resolveDefaultBaseUrl(),
    wsBaseUrl: resolveDefaultWsBaseUrl(),
    authMode: "none",
    token: "",
    apiKey: ""
  });

  const baseUrl = ref<string>(stored.baseUrl ?? "");
  const wsBaseUrl = ref<string>(stored.wsBaseUrl ?? "");
  const authMode = ref<AuthMode>(stored.authMode ?? "none");
  const token = ref<string>(stored.token ?? "");
  const apiKey = ref<string>(stored.apiKey ?? "");
  const status = ref<ConnectionStatus>("unknown");
  const statusMessage = ref<string>("");
  const authStatus = ref<AuthStatus>("unknown");
  const authMessage = ref<string>("");
  const wsConnections = ref(0);

  const resolveUrl = (path: string): string => {
    const origin = baseUrl.value || (isFileOrigin() ? DEFAULT_LOCAL_HTTP : window.location.origin);
    return `${origin}${path}`;
  };

  const resolveWsUrl = (path: string): string => {
    if (wsBaseUrl.value) {
      return `${wsBaseUrl.value}${path}`;
    }
    const origin = baseUrl.value || (isFileOrigin() ? DEFAULT_LOCAL_HTTP : window.location.origin);
    const scheme = origin.startsWith("https") ? "wss" : "ws";
    const host = origin.replace(/^https?:\/\//, "");
    return `${scheme}://${host}${path}`;
  };

  const authHeader = computed(() => {
    if (authMode.value === "bearer" || authMode.value === "both") {
      return token.value ? `Bearer ${token.value}` : "";
    }
    return "";
  });

  const baseUrlDisplay = computed(() => {
    if (baseUrl.value) {
      return baseUrl.value;
    }
    if (isFileOrigin()) {
      return DEFAULT_LOCAL_HTTP;
    }
    return "(same origin)";
  });
  const statusLabel = computed(() => {
    if (status.value === "online") {
      return "Online";
    }
    if (status.value === "offline") {
      return "Offline";
    }
    return "Unknown";
  });

  const wsLabel = computed(() => (wsConnections.value > 0 ? "Live" : "Polling"));
  const authLabel = computed(() => {
    if (authStatus.value === "unauthenticated") {
      return "Not authenticated";
    }
    if (authStatus.value === "forbidden") {
      return "Forbidden";
    }
    return "";
  });

  const setOffline = (message: string) => {
    status.value = "offline";
    statusMessage.value = message;
  };

  const setOnline = () => {
    status.value = "online";
    statusMessage.value = "";
    if (authStatus.value !== "unauthenticated" && authStatus.value !== "forbidden") {
      authStatus.value = "ok";
      authMessage.value = "";
    }
  };

  const setAuthStatus = (next: AuthStatus, message?: string) => {
    authStatus.value = next;
    authMessage.value = message ?? "";
  };

  const registerWsConnection = () => {
    wsConnections.value += 1;
  };

  const unregisterWsConnection = () => {
    wsConnections.value = Math.max(0, wsConnections.value - 1);
  };

  const persist = () => {
    saveJson(STORAGE_KEY, {
      baseUrl: baseUrl.value,
      wsBaseUrl: wsBaseUrl.value,
      authMode: authMode.value,
      token: token.value,
      apiKey: apiKey.value
    });
  };

  return {
    baseUrl,
    wsBaseUrl,
    authMode,
    token,
    apiKey,
    status,
    statusMessage,
    authStatus,
    authMessage,
    resolveUrl,
    resolveWsUrl,
    authHeader,
    baseUrlDisplay,
    statusLabel,
    wsLabel,
    authLabel,
    setOffline,
    setOnline,
    setAuthStatus,
    registerWsConnection,
    unregisterWsConnection,
    persist
  };
});
