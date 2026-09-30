import { useConnectionStore } from "../stores/connection";
import { mockFetch } from "./mock";
import { assertSecureTransport } from "../utils/transport-security";

export interface ApiError extends Error { status?: number; body?: unknown }
export interface RequestOptions {
  method?: string; body?: unknown; timeoutMs?: number; retries?: number;
  skipAuthValidation?: boolean; suppressAuthStatus?: boolean; signal?: AbortSignal;
}
const DEFAULT_TIMEOUT = 30000;
const DEFAULT_RETRIES = 2;
const MAX_RESPONSE_BYTES = 8 * 1024 * 1024;
const USE_MOCK = import.meta.env.VITE_RTH_MOCK === "true";
const createError = (message: string, status?: number, body?: unknown): ApiError =>
  Object.assign(new Error(message), { status, body });
const asError = (error: unknown): ApiError => error instanceof Error || error instanceof DOMException
  ? error as ApiError : createError("Unknown error");
const errorMessageFromBody = (body: unknown, fallback: string) => {
  if (body && typeof body === "object") {
    for (const key of ["detail", "message", "error"]) {
      const value = (body as Record<string, unknown>)[key];
      if (typeof value === "string" && value.trim()) { return value; }
    }
  }
  return typeof body === "string" && body.trim() ? body : fallback;
};
const assertCurrent = (identity: string) => {
  if (identity !== useConnectionStore().requestIdentity) {
    throw new DOMException("Connection settings changed", "AbortError");
  }
};
const awaitWithAbort = async <T>(promise: Promise<T>, signal: AbortSignal): Promise<T> => {
  signal.throwIfAborted();
  let abort!: () => void;
  const cancelled = new Promise<T>((_, reject) => {
    abort = () => reject(signal.reason);
    signal.addEventListener("abort", abort, { once: true });
  });
  try { return await Promise.race([promise, cancelled]); }
  finally { signal.removeEventListener("abort", abort); }
};
const withRequestOwner = async <T>(options: RequestOptions, work: (owned: RequestOptions & { signal: AbortSignal }) => Promise<T>): Promise<T> => {
  const controller = new AbortController();
  const abort = () => controller.abort(options.signal?.reason);
  options.signal?.throwIfAborted();
  options.signal?.addEventListener("abort", abort, { once: true });
  const timer = window.setTimeout(() => controller.abort(new DOMException("Request timed out", "TimeoutError")), options.timeoutMs ?? DEFAULT_TIMEOUT);
  try { return await work({ ...options, signal: controller.signal }); }
  finally { window.clearTimeout(timer); options.signal?.removeEventListener("abort", abort); }
};
const readBody = async (response: Response, signal: AbortSignal, identity: string): Promise<Uint8Array<ArrayBuffer>[]> => {
  const reader = response.body?.getReader();
  if (!reader) { signal.throwIfAborted(); assertCurrent(identity); return []; }
  const chunks: Uint8Array<ArrayBuffer>[] = [];
  let length = 0;
  try {
    while (true) {
      const chunk = await awaitWithAbort(reader.read(), signal);
      signal.throwIfAborted(); assertCurrent(identity);
      if (chunk.done) { break; }
      length += chunk.value.byteLength;
      if (length > MAX_RESPONSE_BYTES) { throw createError("Response exceeds the 8 MiB download limit.", 413); }
      chunks.push(new Uint8Array(chunk.value));
    }
    return chunks;
  } finally {
    void reader.cancel().catch((error) => console.warn("Unable to cancel response body", error));
  }
};
const readText = async (response: Response, signal: AbortSignal, identity: string): Promise<string> => {
  const chunks = await readBody(response, signal, identity);
  const decoder = new TextDecoder();
  return chunks.map((chunk) => decoder.decode(chunk, { stream: true })).join("") + decoder.decode();
};
const buildHeaders = (body: unknown): Record<string, string> => {
  const connection = useConnectionStore();
  const headers: Record<string, string> = {};
  if (connection.authHeader) { headers.Authorization = connection.authHeader; }
  if ((connection.authMode === "apiKey" || connection.authMode === "both") && connection.apiKey) {
    headers["X-API-Key"] = connection.apiKey;
  }
  if (typeof body === "string") { headers["Content-Type"] = "text/plain"; }
  else if (body !== undefined && !(body instanceof FormData)) { headers["Content-Type"] = "application/json"; }
  return headers;
};
const buildRequestInit = (options: RequestOptions): RequestInit => {
  const init: RequestInit = {
    method: options.method ?? "GET", headers: buildHeaders(options.body),
    redirect: "error", credentials: "omit", signal: options.signal
  };
  if (options.body !== undefined) {
    init.body = typeof options.body === "string" || options.body instanceof FormData ? options.body : JSON.stringify(options.body);
  }
  return init;
};
const shouldRetry = (method: string, error: ApiError) => method.toUpperCase() === "GET" && (error.status === undefined || error.status >= 500);
const delay = async (ms: number, signal: AbortSignal) => {
  let timer: number | undefined;
  try { await awaitWithAbort(new Promise<void>((resolve) => { timer = window.setTimeout(resolve, ms); }), signal); }
  finally { window.clearTimeout(timer); }
};
const requestRaw = async (path: string, options: RequestOptions & { signal: AbortSignal }, identity: string): Promise<Response> => {
  const connection = useConnectionStore();
  const url = connection.resolveUrl(path);
  assertSecureTransport(url, "http");
  if (!options.skipAuthValidation && connection.isRemoteTarget && !connection.hasValidAuthConfig()) {
    const message = connection.authValidationError || "Remote backend requires authentication.";
    connection.setAuthStatus("unauthenticated", message);
    throw createError(message, 401, { message });
  }
  const init = buildRequestInit(options);
  const maxRetries = options.retries ?? (init.method?.toUpperCase() === "GET" ? DEFAULT_RETRIES : 0);
  let attempt = 0;
  while (true) {
    options.signal.throwIfAborted(); assertCurrent(identity);
    try {
      const response = await awaitWithAbort(USE_MOCK
        ? mockFetch(path, { method: init.method, body: options.body })
        : fetch(url, init), options.signal);
      if (identity !== connection.requestIdentity) {
        if (response.body) { void response.body.cancel().catch((error) => console.warn("Unable to cancel stale response", error)); }
        assertCurrent(identity);
      }
      if (!response.ok) {
        const text = await readText(response, options.signal, identity);
        let body: unknown = text;
        try { body = text ? JSON.parse(text) : undefined; } catch { /* Plain-text error responses are supported. */ }
        throw createError(errorMessageFromBody(body, `Request failed: ${response.status}`), response.status, body);
      }
      connection.setOnline();
      return response;
    } catch (failure) {
      const error = asError(failure);
      if (options.signal.aborted || error.name === "AbortError" || identity !== connection.requestIdentity) { throw error; }
      if (!options.suppressAuthStatus && error.status === 401) { connection.setAuthStatus("unauthenticated", "Authentication required."); }
      else if (!options.suppressAuthStatus && error.status === 403) { connection.setAuthStatus("forbidden", "Access denied."); }
      else if (!error.status && (init.method ?? "GET").toUpperCase() === "GET") { connection.setOffline(error.message || "Unable to reach the hub"); }
      if (attempt < maxRetries && shouldRetry(init.method ?? "GET", error)) {
        await delay(Math.min(1000 * 2 ** attempt, 4000), options.signal); attempt += 1; continue;
      }
      throw error;
    }
  }
};
export const request = async <T>(path: string, options: RequestOptions = {}): Promise<T> => {
  const identity = useConnectionStore().requestIdentity;
  return withRequestOwner(options, async (owned) => {
    const response = await requestRaw(path, owned, identity);
    const text = await readText(response, owned.signal, identity);
    owned.signal.throwIfAborted(); assertCurrent(identity);
    if (response.status === 204) { return undefined as T; }
    return (response.headers.get("content-type")?.includes("application/json") ? JSON.parse(text) : text) as T;
  });
};
export const getBlob = async (path: string, options: RequestOptions = {}): Promise<Blob> => {
  const identity = useConnectionStore().requestIdentity;
  return withRequestOwner(options, async (owned) => {
    const response = await requestRaw(path, owned, identity);
    return new Blob(await readBody(response, owned.signal, identity), { type: response.headers.get("content-type") ?? "application/octet-stream" });
  });
};
export const get = async <T>(path: string, options: RequestOptions = {}): Promise<T> => request<T>(path, options);
export const post = async <T>(path: string, body?: unknown, options: Omit<RequestOptions, "method" | "body"> = {}): Promise<T> => request<T>(path, { ...options, method: "POST", body });
export const put = async <T>(path: string, body?: unknown): Promise<T> => request<T>(path, { method: "PUT", body });
export const patch = async <T>(path: string, body?: unknown): Promise<T> => request<T>(path, { method: "PATCH", body });
export const del = async <T>(path: string, options: Omit<RequestOptions, "method" | "body"> = {}): Promise<T> => request<T>(path, { ...options, method: "DELETE" });
