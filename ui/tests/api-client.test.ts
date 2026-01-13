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
    await expect(request("/Status")).rejects.toBeDefined();
    expect(connectionStore.authStatus).toBe("unauthenticated");
  });
});
