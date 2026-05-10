import { beforeEach, describe, expect, it } from "vitest";
import { createPinia, setActivePinia } from "pinia";

import { useConnectionPills } from "../src/composables/useConnectionPills";
import { useConnectionStore } from "../src/stores/connection";

describe("useConnectionPills", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("maps connection status to status pill classes", () => {
    const store = useConnectionStore();
    const pills = useConnectionPills();

    store.status = "unknown";
    expect(pills.connectionClass.value).toBe("cui-status-accent");

    store.status = "online";
    expect(pills.connectionClass.value).toBe("cui-status-success");

    store.status = "offline";
    expect(pills.connectionClass.value).toBe("cui-status-danger");
  });

  it("maps websocket state to live/polling classes", () => {
    const store = useConnectionStore();
    const pills = useConnectionPills();

    expect(pills.wsLabel.value).toBe("Polling");
    expect(pills.wsClass.value).toBe("cui-status-accent");

    store.registerWsConnection();
    expect(pills.wsLabel.value).toBe("Live");
    expect(pills.wsClass.value).toBe("cui-status-success");

    store.unregisterWsConnection();
    expect(pills.wsLabel.value).toBe("Polling");
    expect(pills.wsClass.value).toBe("cui-status-accent");
  });
});
