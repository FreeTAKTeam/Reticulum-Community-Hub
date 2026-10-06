import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { createMemoryHistory, createRouter } from "vue-router";
import { useConnectionStore } from "../stores/connection";
import { requireSession } from "./session-guard";
import { get } from "../api/client";

const savedConnection = (rememberSecrets = true, baseUrl = "http://localhost:18000") => {
  localStorage.setItem("rth-ui-connection", JSON.stringify({
    baseUrl, authMode: "apiKey", apiKey: "disposable-fixture", rememberSecrets
  }));
  setActivePinia(createPinia());
  return useConnectionStore();
};
const routerForSession = () => {
  const component = { template: "<div />" };
  const router = createRouter({ history: createMemoryHistory(), routes:
    ["chat", "topics", "files", "connect", "about"].map((name) => ({ path: `/${name}`, name, component }))
  });
  router.beforeEach(requireSession);
  return router;
};
const jsonResponse = (status = 200) => new Response(JSON.stringify({ status: "ok" }), {
  status, headers: { "Content-Type": "application/json" }
});

describe("protected navigation and remembered sessions", () => {
  beforeEach(() => { localStorage.clear(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

  it.each(["http://localhost:18000", "https://hub.example"])("revalidates saved credentials before entering the requested route at %s", async (origin) => {
    const connection = savedConnection(true, origin);
    let finish!: (response: Response) => void;
    const fetch = vi.fn<typeof globalThis.fetch>(() => new Promise<Response>((resolve) => { finish = resolve; }));
    vi.stubGlobal("fetch", fetch);
    const router = routerForSession();
    const navigation = router.push("/chat?topic=field#latest");
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledOnce());
    expect(connection.hasActiveAuthSession).toBe(false);
    expect(router.currentRoute.value.path).not.toBe("/chat");
    finish(jsonResponse());
    await navigation;
    expect(router.currentRoute.value.fullPath).toBe("/chat?topic=field#latest");
    expect(connection.hasActiveAuthSession).toBe(true);
    expect(fetch.mock.calls[0][0]).toBe(`${origin}/Status`);
    expect(fetch.mock.calls[0][1]).toMatchObject({ headers: { "X-API-Key": "disposable-fixture" }, credentials: "omit", redirect: "error" });
    await router.push("/topics"); await router.push("/files"); await router.push("/chat");
    expect(router.currentRoute.value.path).toBe("/chat");
    expect(fetch).toHaveBeenCalledOnce();
    expect(localStorage.getItem("rth-ui-connection")).not.toContain("isAuthenticated");
  });

  it("validates again in a new application instance instead of trusting saved session state", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse()));
    for (let tab = 0; tab < 2; tab += 1) {
      const connection = savedConnection();
      expect(connection.hasActiveAuthSession).toBe(false);
      const router = routerForSession(); await router.push("/chat");
      expect(connection.hasActiveAuthSession).toBe(true);
    }
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it("keeps persistence opt-in and redirects with the full requested route", async () => {
    const connection = savedConnection(false);
    vi.stubGlobal("fetch", vi.fn());
    expect(connection.apiKey).toBe("");
    const router = routerForSession(); await router.push("/chat?topic=field");
    expect(router.currentRoute.value.path).toBe("/connect");
    expect(router.currentRoute.value.query.redirect).toBe("/chat?topic=field");
    expect(fetch).not.toHaveBeenCalled();
    connection.apiKey = "memory-only-fixture"; connection.persist(false);
    expect(localStorage.getItem("rth-ui-connection")).not.toContain("memory-only-fixture");
  });

  it.each([401, 403])("rejects saved credentials denied with %s and does not retry them on navigation", async (status) => {
    const connection = savedConnection();
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(status)));
    const router = routerForSession(); await router.push("/chat"); await router.push("/topics");
    expect(connection.hasActiveAuthSession).toBe(false);
    expect(connection.authStatus).toBe("unauthenticated");
    expect(router.currentRoute.value.path).toBe("/connect");
    expect(fetch).toHaveBeenCalledOnce();
  });

  it("does not restore a revoked session after a genuine 401", async () => {
    const connection = savedConnection();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(jsonResponse()).mockResolvedValueOnce(jsonResponse(401)));
    const router = routerForSession(); await router.push("/chat");
    await expect(get("/Topic", { retries: 0 })).rejects.toMatchObject({ status: 401 });
    await router.push("/files");
    expect(connection.hasActiveAuthSession).toBe(false);
    expect(router.currentRoute.value.path).toBe("/connect");
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it.each(["origin", "websocket", "mode", "credential", "away and back"])("ignores a stale successful validation after changing %s", async (change) => {
    const connection = savedConnection();
    let finish!: (response: Response) => void;
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((resolve) => { finish = resolve; })));
    const router = routerForSession(); const navigation = router.push("/chat");
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledOnce());
    const identity = connection.requestIdentity;
    if (change === "origin") { connection.baseUrl = "https://new.example"; }
    if (change === "websocket") { connection.wsBaseUrl = "wss://events.example"; }
    if (change === "mode") { connection.authMode = "bearer"; }
    if (change === "credential") { connection.apiKey = "replacement"; }
    if (change === "away and back") { connection.apiKey = "replacement"; connection.apiKey = "disposable-fixture"; }
    expect(connection.requestIdentity).not.toBe(identity);
    finish(jsonResponse()); await navigation;
    expect(connection.hasActiveAuthSession).toBe(false);
    expect(router.currentRoute.value.path).toBe("/connect");
    expect(connection.authStatus).toBe("unknown");
  });

  it("keeps secure transport enforcement during remembered login", async () => {
    savedConnection(true, "http://remote.example");
    vi.stubGlobal("fetch", vi.fn());
    const router = routerForSession(); await router.push("/chat");
    expect(router.currentRoute.value.path).toBe("/connect");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("does not validate credentials just to visit a public route", async () => {
    savedConnection(); vi.stubGlobal("fetch", vi.fn());
    const router = routerForSession(); await router.push("/about");
    expect(fetch).not.toHaveBeenCalled();
  });
});
