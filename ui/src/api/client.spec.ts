// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

import { get, getBlob, post } from "./client";
import { useConnectionStore } from "../stores/connection";

describe("api client remote auth gating", () => {
  beforeEach(() => {
    window.localStorage.clear();
    setActivePinia(createPinia());
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
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

  it("never sends a credential or setup password over remote HTTP, including bootstrap requests", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const connection = useConnectionStore();
    connection.baseUrl = "http://remote.example:8000";
    connection.authMode = "apiKey";
    connection.apiKey = "fixture-key";
    await expect(get("/Status", { skipAuthValidation: true, retries: 0 })).rejects.toThrow(/HTTPS/);
    await expect(post("/api/r3akt/setup/complete", { remote_password: "fixture-password" }, { skipAuthValidation: true })).rejects.toThrow(/HTTPS/);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("does not apply an old target's rejection to an authenticated new target", async () => {
    let finish!: (response: Response) => void;
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((resolve) => { finish = resolve; })));
    const connection = useConnectionStore();
    connection.baseUrl = "https://old.example";
    connection.authMode = "apiKey";
    connection.apiKey = "old-fixture";
    const pending = get("/Status", { retries: 0 });
    connection.baseUrl = "https://new.example";
    connection.apiKey = "new-fixture";
    connection.markAuthenticated();
    connection.setOnline();
    finish(new Response("Unauthorized", { status: 401 }));
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
    expect(connection.hasActiveAuthSession).toBe(true);
    expect(connection.authStatus).toBe("ok");
    expect(connection.status).toBe("online");
  });

  it("cancels an attachment body when its request owner is aborted", async () => {
    const cancelled = vi.fn();
    vi.stubGlobal("fetch", vi.fn(async () => new Response(new ReadableStream({ cancel: cancelled }))));
    const controller = new AbortController();
    const pending = getBlob("/Image/1/raw", { signal: controller.signal, retries: 0 });
    await new Promise((resolve) => setTimeout(resolve, 0));
    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
    expect(cancelled).toHaveBeenCalledOnce();
  });

  it("rejects a successful response from a replaced target", async () => {
    let finish!: (response: Response) => void;
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((resolve) => { finish = resolve; })));
    const connection = useConnectionStore();
    connection.baseUrl = "https://old.example";
    connection.authMode = "apiKey"; connection.apiKey = "fixture";
    const pending = get("/File", { retries: 0 });
    connection.baseUrl = "https://new.example";
    finish(new Response("[]", { headers: { "content-type": "application/json" } }));
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
    expect(connection.status).toBe("unknown");
  });

  it("rejects an old target's body that completes after the connection changes", async () => {
    let body!: ReadableStreamDefaultController<Uint8Array>;
    vi.stubGlobal("fetch", vi.fn(async () => new Response(new ReadableStream({ start(controller) { body = controller; } }), { headers: { "content-type": "application/json" } })));
    const connection = useConnectionStore();
    connection.baseUrl = "https://old.example";
    connection.authMode = "apiKey"; connection.apiKey = "fixture";
    const pending = get("/File", { retries: 0 });
    await new Promise((resolve) => setTimeout(resolve, 0));
    connection.baseUrl = "https://new.example";
    body.enqueue(new TextEncoder().encode('[{"FileID":1}]')); body.close();
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
  });

  it("keeps a stalled JSON body within cancellation and deadline ownership", async () => {
    const cancelled = vi.fn();
    vi.stubGlobal("fetch", vi.fn(async () => new Response(new ReadableStream({ cancel: cancelled }), { headers: { "content-type": "application/json" } })));
    const controller = new AbortController();
    const pending = get("/Status", { signal: controller.signal, retries: 0 });
    await new Promise((resolve) => setTimeout(resolve, 0));
    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
    expect(cancelled).toHaveBeenCalledOnce();
    await expect(get("/Status", { timeoutMs: 10, retries: 0 })).rejects.toMatchObject({ name: "TimeoutError" });
    expect(cancelled).toHaveBeenCalledTimes(2);
  });

  it("rejects over-limit downloads before retaining unbounded data", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(new Uint8Array(8 * 1024 * 1024 + 1))));
    await expect(getBlob("/File/1/raw", { retries: 0 })).rejects.toMatchObject({ status: 413 });
  });
});
