import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useConnectionStore } from "../src/stores/connection";
import { request } from "../src/api/client";

describe("api client", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it("injects auth headers", async () => {
    const connectionStore = useConnectionStore();
    connectionStore.authMode = "both";
    connectionStore.token = "token-123";
    connectionStore.apiKey = "key-456";

    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" }
      })
    );
    globalThis.fetch = fetchMock as any;

    await request("/Status");

    const init = fetchMock.mock.calls[0][1] as RequestInit;
    const headers = init.headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer token-123");
    expect(headers["X-API-Key"]).toBe("key-456");
  });

  it("retries GET on server error", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response("oops", { status: 500 }))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        })
      );
    globalThis.fetch = fetchMock as any;

    const promise = request<{ ok: boolean }>("/Status");
    await vi.runAllTimersAsync();
    const data = await promise;

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(data.ok).toBe(true);
  });

  it("sets auth status on 401", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "unauthorized" }), {
        status: 401,
        headers: { "Content-Type": "application/json" }
      })
    );
    globalThis.fetch = fetchMock as any;

    const connectionStore = useConnectionStore();
    await expect(request("/Status", { retries: 0 })).rejects.toMatchObject({
      status: 401,
      message: "unauthorized",
      body: { detail: "unauthorized" }
    });
    expect(connectionStore.authStatus).toBe("unauthenticated");
  });

  it("preserves text error status and body", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response("invalid topic", {
        status: 400,
        headers: { "Content-Type": "text/plain" }
      })
    ) as any;

    await expect(request("/Topic", { retries: 0 })).rejects.toMatchObject({
      status: 400,
      message: "invalid topic",
      body: "invalid topic"
    });
  });

  it("preserves malformed JSON error text", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response("{not-json", {
        status: 500,
        headers: { "Content-Type": "application/json" }
      })
    ) as any;

    await expect(request("/Status", { retries: 0 })).rejects.toMatchObject({
      status: 500,
      message: "{not-json",
      body: "{not-json"
    });
  });

  it("sets forbidden auth state without losing the server detail", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "operator role required" }), {
        status: 403,
        headers: { "Content-Type": "application/json" }
      })
    ) as any;

    const connectionStore = useConnectionStore();
    await expect(request("/Status", { retries: 0 })).rejects.toMatchObject({
      status: 403,
      message: "operator role required"
    });
    expect(connectionStore.authStatus).toBe("forbidden");
  });
});
