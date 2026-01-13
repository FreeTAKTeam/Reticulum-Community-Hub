import { useConnectionStore } from "../stores/connection";

export interface ApiError extends Error {
  status?: number;
  body?: unknown;
}

export interface RequestOptions {
  method?: string;
  body?: unknown;
  timeoutMs?: number;
}

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

export const request = async <T>(path: string, options: RequestOptions = {}): Promise<T> => {
  const connectionStore = useConnectionStore();
  const url = connectionStore.resolveUrl(path);
  const headers: Record<string, string> = {};

  const authHeader = connectionStore.authHeader;
  if (authHeader) {
    headers.Authorization = authHeader;
  }
  if ((connectionStore.authMode === "apiKey" || connectionStore.authMode === "both") && connectionStore.apiKey) {
    headers["X-API-Key"] = connectionStore.apiKey;
  }

  const requestInit: RequestInit = {
    method: options.method ?? "GET",
    headers
  };
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    requestInit.body = JSON.stringify(options.body);
  }

  try {
    const response = await withTimeout(fetch(url, requestInit), options.timeoutMs ?? 10000);
    if (!response.ok) {
      let errorBody: unknown = undefined;
      try {
        errorBody = await response.json();
      } catch (error) {
        errorBody = await response.text();
      }
      throw createError(`Request failed: ${response.status}`, response.status, errorBody);
    }
    if (response.status === 204) {
      return undefined as T;
    }
    const contentType = response.headers.get("content-type") ?? "";
    if (contentType.includes("application/json")) {
      return (await response.json()) as T;
    }
    return (await response.text()) as T;
  } catch (error) {
    connectionStore.setOffline(error instanceof Error ? error.message : "Unknown error");
    throw error;
  }
};

export const get = async <T>(path: string): Promise<T> => request<T>(path);

export const post = async <T>(path: string, body?: unknown): Promise<T> =>
  request<T>(path, { method: "POST", body });

export const put = async <T>(path: string, body?: unknown): Promise<T> =>
  request<T>(path, { method: "PUT", body });

export const patch = async <T>(path: string, body?: unknown): Promise<T> =>
  request<T>(path, { method: "PATCH", body });

export const del = async <T>(path: string): Promise<T> => request<T>(path, { method: "DELETE" });
