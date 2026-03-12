import { describe, expect, it } from "vitest";

import {
  cycleMissionMemberStatus,
  deriveMissionMemberOverallStatus,
  createUnknownMissionMemberStatus,
  toMissionMemberStatusSummary
} from "./mission-member-status";

describe("toMissionMemberStatusSummary", () => {
  it("derives capability from the deprecated alias and computes a folded score", () => {
    const summary = toMissionMemberStatusSummary({
      subjectType: "member",
      subjectId: "member-1",
      teamId: "team-1",
      reportedAt: "2026-03-11T10:00:00Z",
      securityStatus: "Yellow",
      securityCapability: "Unknown",
      preparednessStatus: "Yellow",
      medicalStatus: "Green",
      mobilityStatus: "Green",
      commsStatus: "Green"
    });

    expect(summary.capabilityStatus).toBe("Unknown");
    expect(summary.overallStatus).toBe("Yellow");
    expect(summary.scorePercent).toBe(67);
  });

  it("treats expired snapshots as unknown for the mission dashboard", () => {
    const summary = toMissionMemberStatusSummary(
      {
        subjectType: "member",
        subjectId: "member-1",
        teamId: "team-1",
        reportedAt: "2026-03-11T10:00:00Z",
        ttlSeconds: 60,
        overallStatus: "Green",
        securityStatus: "Green",
        capabilityStatus: "Green",
        preparednessStatus: "Green",
        medicalStatus: "Green",
        mobilityStatus: "Green",
        commsStatus: "Green"
      },
      { referenceTimeMs: Date.parse("2026-03-11T10:02:00Z") }
    );

    expect(summary.isExpired).toBe(true);
    expect(summary.overallStatus).toBe("Unknown");
    expect(summary.scorePercent).toBe(0);
  });

  it("does not treat a null ttl as immediately expired", () => {
    const summary = toMissionMemberStatusSummary({
      subjectType: "member",
      subjectId: "member-1",
      teamId: "team-1",
      reportedAt: "2026-03-11T10:00:00Z",
      ttlSeconds: null,
      overallStatus: "Green",
      securityStatus: "Green",
      capabilityStatus: "Unknown",
      preparednessStatus: "Unknown",
      medicalStatus: "Unknown",
      mobilityStatus: "Unknown",
      commsStatus: "Unknown"
    });

    expect(summary.isExpired).toBe(false);
    expect(summary.overallStatus).toBe("Green");
    expect(summary.scorePercent).toBe(17);
  });

  it("returns an all-unknown baseline when no report exists", () => {
    expect(createUnknownMissionMemberStatus()).toEqual({
      overallStatus: "Unknown",
      securityStatus: "Unknown",
      capabilityStatus: "Unknown",
      preparednessStatus: "Unknown",
      medicalStatus: "Unknown",
      mobilityStatus: "Unknown",
      commsStatus: "Unknown",
      scorePercent: 0,
      reportedAt: "",
      ttlSeconds: null,
      isExpired: false
    });
  });

  it("cycles statuses in the requested order", () => {
    expect(cycleMissionMemberStatus("Unknown")).toBe("Green");
    expect(cycleMissionMemberStatus("Green")).toBe("Yellow");
    expect(cycleMissionMemberStatus("Yellow")).toBe("Red");
    expect(cycleMissionMemberStatus("Red")).toBe("Unknown");
  });

  it("derives overall status conservatively from the dimensions", () => {
    expect(deriveMissionMemberOverallStatus(["Unknown", "Green", "Green"])).toBe("Unknown");
    expect(deriveMissionMemberOverallStatus(["Green", "Yellow", "Green"])).toBe("Yellow");
    expect(deriveMissionMemberOverallStatus(["Green", "Red", "Green"])).toBe("Red");
  });
});
