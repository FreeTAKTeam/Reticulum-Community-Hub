import { useConnectionStore } from "../stores/connection";
import { mockFetch } from "./mock";

export interface ApiError extends Error {
  status?: number;
  body?: unknown;
}

export interface RequestOptions {
  method?: string;
  body?: unknown;
  timeoutMs?: number;
  retries?: number;
}

const DEFAULT_TIMEOUT = 10000;
const DEFAULT_RETRIES = 2;
const USE_MOCK = import.meta.env.VITE_RTH_MOCK === "true";

const createError = (message: string, status?: number, body?: unknown): ApiError => {
  const error = new Error(message) as ApiError;
  error.status = status;
  error.body = body;
  return error;
};

const withTimeout = async (promise: Promise<Response>, timeoutMs: number): Promise<Response> => {
  let timeoutId: number | undefined;
  const timeoutPromise = new Promise<Response>((_, reject) => {
    timeoutId = window.setTimeout(() => {
      reject(createError("Request timed out"));
    }, timeoutMs);
  });
  const response = await Promise.race([promise, timeoutPromise]);
  if (timeoutId) {
    clearTimeout(timeoutId);
  }
  return response as Response;
};

const delay = (ms: number) =>
  new Promise<void>((resolve) => {
    window.setTimeout(() => resolve(), ms);
  });

const buildHeaders = (body: unknown): Record<string, string> => {
  const connectionStore = useConnectionStore();
  const headers: Record<string, string> = {};
  const authHeader = connectionStore.authHeader;
  if (authHeader) {
    headers.Authorization = authHeader;
  }
  if ((connectionStore.authMode === "apiKey" || connectionStore.authMode === "both") && connectionStore.apiKey) {
    headers["X-API-Key"] = connectionStore.apiKey;
  }
  if (typeof body === "string") {
    headers["Content-Type"] = "text/plain";
  } else if (body !== undefined && !(body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  return headers;
};

const buildRequestInit = (options: RequestOptions, headers: Record<string, string>): RequestInit => {
  const requestInit: RequestInit = {
    method: options.method ?? "GET",
    headers
  };
  if (options.body !== undefined) {
    if (typeof options.body === "string") {
      requestInit.body = options.body;
    } else if (options.body instanceof FormData) {
      requestInit.body = options.body;
    } else {
      requestInit.body = JSON.stringify(options.body);
    }
  }
  return requestInit;
};

const shouldRetry = (method: string, error: ApiError) => {
  if (method.toUpperCase() !== "GET") {
    return false;
  }
  if (error.status === undefined) {
    return true;
  }
  return error.status >= 500;
};

const requestRaw = async (path: string, options: RequestOptions = {}): Promise<Response> => {
  const connectionStore = useConnectionStore();
  const url = connectionStore.resolveUrl(path);
  const headers = buildHeaders(options.body);
  const requestInit = buildRequestInit(options, headers);
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT;
  const maxRetries =
    options.retries ?? (requestInit.method?.toUpperCase() === "GET" ? DEFAULT_RETRIES : 0);

  let attempt = 0;
  while (true) {
    try {
      const response = USE_MOCK
        ? await mockFetch(path, { method: requestInit.method, body: options.body })
        : await withTimeout(fetch(url, requestInit), timeoutMs);
      if (!response.ok) {
        let errorBody: unknown = undefined;
        try {
          errorBody = await response.json();
        } catch (error) {
          errorBody = await response.text();
        }
        throw createError(`Request failed: ${response.status}`, response.status, errorBody);
      }
      connectionStore.setOnline();
      connectionStore.setAuthStatus("ok");
      return response;
    } catch (error) {
      const apiError = error instanceof Error ? (error as ApiError) : createError("Unknown error");
      if (apiError.status === 401) {
        connectionStore.setAuthStatus("unauthenticated", "Authentication required.");
      } else if (apiError.status === 403) {
        connectionStore.setAuthStatus("forbidden", "Access denied.");
      } else if (!apiError.status) {
        connectionStore.setOffline(apiError.message || "Unable to reach the hub");
      }
      if (attempt < maxRetries && shouldRetry(requestInit.method ?? "GET", apiError)) {
        const backoff = Math.min(1000 * 2 ** attempt, 4000);
        attempt += 1;
        await delay(backoff);
        continue;
      }
      throw apiError;
    }
  }
};

export const request = async <T>(path: string, options: RequestOptions = {}): Promise<T> => {
  const response = await requestRaw(path, options);
  if (response.status === 204) {
    return undefined as T;
  }
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    return (await response.json()) as T;
  }
  return (await response.text()) as T;
};

export const getBlob = async (path: string, options: RequestOptions = {}): Promise<Blob> => {
  const response = await requestRaw(path, options);
  return response.blob();
};

export const get = async <T>(path: string): Promise<T> => request<T>(path);

export const post = async <T>(path: string, body?: unknown): Promise<T> =>
  request<T>(path, { method: "POST", body });

export const put = async <T>(path: string, body?: unknown): Promise<T> =>
  request<T>(path, { method: "PUT", body });

export const patch = async <T>(path: string, body?: unknown): Promise<T> =>
  request<T>(path, { method: "PATCH", body });

export const del = async <T>(path: string): Promise<T> => request<T>(path, { method: "DELETE" });
