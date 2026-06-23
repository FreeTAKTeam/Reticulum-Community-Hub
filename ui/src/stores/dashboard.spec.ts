import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";
import { useDashboardStore } from "./dashboard";

describe("dashboard event feed", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
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
});
