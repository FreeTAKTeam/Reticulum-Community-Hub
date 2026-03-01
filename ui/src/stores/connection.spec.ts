// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from "vitest";
import { createPinia, setActivePinia } from "pinia";

import { useConnectionStore } from "./connection";

describe("connection store target and auth validation", () => {
  beforeEach(() => {
    window.localStorage.clear();
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
});
