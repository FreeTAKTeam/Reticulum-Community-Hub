// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from "vitest";
import { createPinia, setActivePinia } from "pinia";

import { useConnectionStore } from "./connection";

describe("connection store target and auth validation", () => {
  beforeEach(() => {
    window.localStorage.clear();
    const env = import.meta.env as Record<string, string | undefined>;
    delete env.VITE_RTH_BASE_URL;
    delete env.VITE_RTH_WS_BASE_URL;
    setActivePinia(createPinia());
  });

  it("treats loopback target as local and allows authMode none", () => {
    const connectionStore = useConnectionStore();
    connectionStore.baseUrl = "http://127.0.0.1:8000";
    connectionStore.authMode = "none";

    expect(connectionStore.isLocalTarget).toBe(true);
    expect(connectionStore.isRemoteTarget).toBe(false);
    expect(connectionStore.authValidationError).toBe("");
    expect(connectionStore.hasValidAuthConfig()).toBe(true);
  });

  it("requires remote auth mode to be bearer, apiKey, or both", () => {
    const connectionStore = useConnectionStore();
    connectionStore.baseUrl = "https://remote.example";
    connectionStore.authMode = "none";

    expect(connectionStore.isRemoteTarget).toBe(true);
    expect(connectionStore.authValidationError).toBe("Remote backend requires authentication.");
    expect(connectionStore.hasValidAuthConfig()).toBe(false);
  });

  it("requires token and api key based on remote auth mode", () => {
    const connectionStore = useConnectionStore();
    connectionStore.baseUrl = "https://remote.example";
    connectionStore.authMode = "both";

    expect(connectionStore.authValidationError).toBe("Bearer token is required for remote backend authentication.");

    connectionStore.token = "abc";
    expect(connectionStore.authValidationError).toBe("API key is required for remote backend authentication.");

    connectionStore.apiKey = "key";
    expect(connectionStore.authValidationError).toBe("");
    expect(connectionStore.hasValidAuthConfig()).toBe(true);
  });

  it("normalizes a redundant stored websocket base url to follow the base url", () => {
    window.localStorage.setItem(
      "rth-ui-connection",
      JSON.stringify({
        baseUrl: "http://10.0.0.5:8000",
        wsBaseUrl: "ws://10.0.0.5:8000",
        authMode: "apiKey",
        apiKey: "secret"
      })
    );

    const connectionStore = useConnectionStore();

    expect(connectionStore.wsBaseUrl).toBe("");
    expect(connectionStore.resolveWsUrl("/events/system")).toBe("ws://10.0.0.5:8000/events/system");

    connectionStore.baseUrl = "http://192.168.1.20:8000";
    expect(connectionStore.resolveWsUrl("/events/system")).toBe("ws://192.168.1.20:8000/events/system");
  });

  it("prefers configured env targets over stale saved browser targets", () => {
    const env = import.meta.env as Record<string, string | undefined>;
    env.VITE_RTH_BASE_URL = "http://134.122.46.48:8000";

    window.localStorage.setItem(
      "rth-ui-connection",
      JSON.stringify({
        baseUrl: "http://127.0.0.1:8000",
        wsBaseUrl: "ws://127.0.0.1:8000",
        authMode: "apiKey",
        apiKey: "secret"
      })
    );

    const connectionStore = useConnectionStore();

    expect(connectionStore.baseUrl).toBe("http://134.122.46.48:8000");
    expect(connectionStore.wsBaseUrl).toBe("");
    expect(connectionStore.resolveWsUrl("/events/system")).toBe("ws://134.122.46.48:8000/events/system");
  });
});
