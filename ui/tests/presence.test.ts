import { describe, expect, it } from "vitest";
import { clientPresenceTag, isPresenceOnline, isRecentlySeen } from "../src/utils/presence";

describe("presence utils", () => {
  const nowMs = Date.parse("2026-02-12T12:00:00.000Z");

  it("treats recently seen clients as online", () => {
    expect(isRecentlySeen("2026-02-12T11:56:30.000Z", { nowMs })).toBe(true);
    expect(clientPresenceTag("2026-02-12T11:56:30.000Z", { nowMs })).toBe("Active");
  });

  it("treats stale clients as offline", () => {
    expect(isRecentlySeen("2026-02-12T11:40:00.000Z", { nowMs })).toBe(false);
    expect(clientPresenceTag("2026-02-12T11:40:00.000Z", { nowMs })).toBe("Seen");
  });

  it("prefers explicit identity status over timestamps", () => {
    expect(
      isPresenceOnline(
        {
          status: "inactive",
          lastSeenAt: "2026-02-12T11:59:59.000Z"
        },
        { nowMs }
      )
    ).toBe(false);
    expect(
      isPresenceOnline(
        {
          status: "active",
          lastSeenAt: "2026-02-12T11:00:00.000Z"
        },
        { nowMs }
      )
    ).toBe(true);
  });
});
