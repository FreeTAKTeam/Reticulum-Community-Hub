import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useDashboardStore } from "./dashboard";

vi.mock("../api/client", () => ({
  get: vi.fn()
}));

vi.mock("./connection", () => ({
  useConnectionStore: () => ({
    setOnline: vi.fn()
  })
}));

vi.mock("./users", () => ({
  useUsersStore: () => ({
    clients: [],
    identities: [],
    remPeers: [],
    fetchUsers: vi.fn().mockResolvedValue(undefined)
  })
}));

import { get } from "../api/client";

const mockedGet = vi.mocked(get);

describe("dashboard event feed", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    mockedGet.mockReset();
  });

  it("removes stale failed delivery events when the same message is superseded", () => {
    const dashboard = useDashboardStore();

    dashboard.pushEvent({
      id: "failed-event",
      timestamp: "2026-06-23T02:30:00.000Z",
      type: "message_delivery_failed",
      message: "Message delivery failed for unknown",
      metadata: {
        MessageID: "2a2892b3227b427487308d53712dd163",
        State: "failed",
        failure_reason: "send_error"
      }
    });
    dashboard.pushEvent({
      id: "superseded-event",
      timestamp: "2026-06-23T02:31:00.000Z",
      type: "message_delivery_superseded",
      message: "Message delivery failure superseded by propagated state",
      metadata: {
        MessageID: "2a2892b3227b427487308d53712dd163",
        State: "propagated",
        original_event_type: "message_delivery_failed",
        delivery_failure_superseded: true
      }
    });

    expect(dashboard.events).toHaveLength(1);
    expect(dashboard.events[0]?.id).toBe("superseded-event");
    expect(dashboard.events[0]?.category).toBe("message_delivery_superseded");
  });

  it("removes stale failed delivery events when the same message later propagates", () => {
    const dashboard = useDashboardStore();

    dashboard.pushEvent({
      id: "failed-event",
      timestamp: "2026-06-23T02:30:00.000Z",
      type: "message_delivery_failed",
      message: "Message delivery failed for unknown",
      metadata: {
        MessageID: "2a2892b3227b427487308d53712dd163",
        State: "failed",
        delivery_method: "propagated",
        failure_reason: "send_error"
      }
    });
    dashboard.pushEvent({
      id: "propagated-event",
      timestamp: "2026-06-23T02:31:00.000Z",
      type: "message_propagated",
      message: "Message accepted for propagation to unknown",
      metadata: {
        message_id: "2a2892b3227b427487308d53712dd163",
        State: "propagated",
        delivery_method: "propagated",
        delivery_policy_reason: "broadcast_direct_timeout_fallback"
      }
    });

    expect(dashboard.events).toHaveLength(1);
    expect(dashboard.events[0]?.id).toBe("propagated-event");
    expect(dashboard.events[0]?.category).toBe("message_propagated");
  });

  it("does not resurrect a failed card after the same message has propagated", () => {
    const dashboard = useDashboardStore();

    dashboard.pushEvent({
      id: "propagated-event",
      timestamp: "2026-06-23T02:31:00.000Z",
      type: "message_propagated",
      message: "Message accepted for propagation to unknown",
      metadata: {
        MessageID: "2a2892b3227b427487308d53712dd163",
        State: "propagated",
        delivery_method: "propagated",
        delivery_policy_reason: "broadcast_direct_timeout_fallback"
      }
    });
    dashboard.pushEvent({
      id: "delayed-failed-event",
      timestamp: "2026-06-23T02:32:00.000Z",
      type: "message_delivery_failed",
      message: "Message delivery failed for unknown",
      metadata: {
        MessageID: "2a2892b3227b427487308d53712dd163",
        State: "failed",
        delivery_method: "propagated",
        delivery_policy_reason: "broadcast_direct_timeout_fallback",
        failure_reason: "send_error"
      }
    });

    expect(dashboard.events).toHaveLength(1);
    expect(dashboard.events[0]?.id).toBe("propagated-event");
    expect(dashboard.events[0]?.category).toBe("message_propagated");
  });

  it("replaces stale in-memory failures with authoritative event snapshots", () => {
    const dashboard = useDashboardStore();

    dashboard.pushEvent({
      id: "failed-event",
      timestamp: "2026-06-23T02:30:00.000Z",
      type: "message_delivery_failed",
      message: "Message delivery failed for unknown",
      metadata: {
        MessageID: "2a2892b3227b427487308d53712dd163",
        State: "failed",
        delivery_method: "propagated",
        failure_reason: "send_error"
      }
    });

    dashboard.replaceEvents([
      {
        id: "current-event",
        timestamp: "2026-06-23T02:31:00.000Z",
        type: "message_propagated",
        message: "Message accepted for propagation to unknown",
        metadata: {
          MessageID: "2a2892b3227b427487308d53712dd163",
          State: "propagated",
          delivery_method: "propagated"
        }
      }
    ]);

    expect(dashboard.events).toHaveLength(1);
    expect(dashboard.events[0]?.id).toBe("current-event");
    expect(dashboard.events[0]?.category).toBe("message_propagated");
  });

  it("uses wrapped Events snapshots to clear stale in-memory delivery failures", async () => {
    const dashboard = useDashboardStore();

    dashboard.pushEvent({
      id: "failed-event",
      timestamp: "2026-06-23T02:30:00.000Z",
      type: "message_delivery_failed",
      message: "Message delivery failed for unknown",
      metadata: {
        MessageID: "2a2892b3227b427487308d53712dd163",
        State: "failed",
        failure_reason: "send_error"
      }
    });

    mockedGet.mockImplementation(async (path: string) => {
      if (path === "/Status") {
        return {};
      }
      if (path === "/api/r3akt/missions") {
        return { value: [] };
      }
      if (path === "/api/r3akt/team-members") {
        return { value: [] };
      }
      if (path.startsWith("/Events")) {
        return {
          value: [
            {
              id: "current-event",
              timestamp: "2026-06-23T02:31:00.000Z",
              type: "message_propagated",
              message: "Message accepted for propagation to unknown",
              metadata: {
                MessageID: "2a2892b3227b427487308d53712dd163",
                State: "propagated",
                delivery_method: "propagated"
              }
            }
          ],
          Count: 1
        };
      }
      return [];
    });

    await dashboard.refresh();

    expect(dashboard.events).toHaveLength(1);
    expect(dashboard.events[0]?.id).toBe("current-event");
    expect(dashboard.events[0]?.category).toBe("message_propagated");
  });
});
