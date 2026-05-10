// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

import { get } from "./client";
import { useConnectionStore } from "../stores/connection";

describe("api client remote auth gating", () => {
  beforeEach(() => {
    window.localStorage.clear();
    setActivePinia(createPinia());
    vi.restoreAllMocks();
  });

  it("short-circuits remote requests when auth configuration is missing", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const connectionStore = useConnectionStore();
    connectionStore.baseUrl = "https://remote.example";
    connectionStore.authMode = "none";

    await expect(get("/api/v1/status")).rejects.toMatchObject({
      status: 401,
      message: "Remote backend requires authentication."
    });
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(connectionStore.authStatus).toBe("unauthenticated");
  });

  it("allows remote requests when credentials satisfy selected auth mode", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { "content-type": "application/json" }
        })
      )
    );

    const connectionStore = useConnectionStore();
    connectionStore.baseUrl = "https://remote.example";
    connectionStore.authMode = "apiKey";
    connectionStore.apiKey = "abc";

    const response = await get<{ ok: boolean }>("/api/v1/status");
    expect(response.ok).toBe(true);
    expect(fetch).toHaveBeenCalledOnce();
  });
});
