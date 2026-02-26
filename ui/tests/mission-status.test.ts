import { describe } from "vitest";
import { expect } from "vitest";
import { it } from "vitest";
import { getMissionStatusLabel } from "../src/pages/missions/mission-status";
import { getMissionStatusTone } from "../src/pages/missions/mission-status";
import { MISSION_STATUS_ENUM } from "../src/pages/missions/mission-status";
import { normalizeMissionStatus } from "../src/pages/missions/mission-status";
import { toMissionStatusValue } from "../src/pages/missions/mission-status";

describe("mission status normalization", () => {
  it("exposes backend-supported mission status enum values", () => {
    expect([...MISSION_STATUS_ENUM]).toEqual([
      "MISSION_ACTIVE",
      "MISSION_PENDING",
      "MISSION_COMPLETED_SUCCESS",
      "MISSION_COMPLETED_FAILED",
      "MISSION_DELETED"
    ]);
  });

  it("maps legacy mission statuses to supported backend values", () => {
    expect(toMissionStatusValue("MISSION_PLANNED")).toBe("MISSION_PENDING");
    expect(toMissionStatusValue("MISSION_STANDBY")).toBe("MISSION_PENDING");
    expect(toMissionStatusValue("MISSION_COMPLETE")).toBe("MISSION_COMPLETED_SUCCESS");
    expect(toMissionStatusValue("MISSION_ARCHIVED")).toBe("MISSION_DELETED");
  });

  it("normalizes display tokens and defaults invalid values to ACTIVE", () => {
    expect(normalizeMissionStatus("mission_completed_failed")).toBe("COMPLETED_FAILED");
    expect(normalizeMissionStatus("not-a-valid-status")).toBe("ACTIVE");
    expect(toMissionStatusValue("")).toBe("MISSION_ACTIVE");
  });

  it("renders user-facing labels for completed mission states", () => {
    expect(getMissionStatusLabel("COMPLETED_FAILED")).toBe("Failed");
    expect(getMissionStatusLabel("COMPLETED_SUCCESS")).toBe("Success");
  });

  it("maps mission states to deterministic cosmic tone classes", () => {
    expect(getMissionStatusTone("MISSION_ACTIVE")).toBe("active");
    expect(getMissionStatusTone("MISSION_PENDING")).toBe("pending");
    expect(getMissionStatusTone("MISSION_COMPLETED_SUCCESS")).toBe("success");
    expect(getMissionStatusTone("MISSION_COMPLETED_FAILED")).toBe("failed");
    expect(getMissionStatusTone("MISSION_DELETED")).toBe("deleted");
  });
});
