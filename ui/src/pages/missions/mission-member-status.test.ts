import { describe, expect, it } from "vitest";

import {
  cycleMissionMemberStatus,
  deriveMissionMemberOverallStatus,
  createUnknownMissionMemberStatus,
  toEmergencyActionMessageRecord,
  toEmergencyActionMessageUpsertPayload,
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

  it("maps snake_case API records to the UI EAM model", () => {
    const mapped = toEmergencyActionMessageRecord({
      callsign: "corvo",
      team_member_uid: "member-7",
      team_uid: "team-9",
      reported_by: "c1d2e3",
      reported_at: "2026-04-08T10:30:00Z",
      ttl_seconds: 120,
      notes: "ready",
      confidence: 0.88,
      source: { rns_identity: "cafebabe" },
      overall_status: "Yellow",
      security_status: "Green",
      capability_status: "Red",
      preparedness_status: "Yellow",
      medical_status: "Green",
      mobility_status: "Unknown",
      comms_status: "Green"
    });

    expect(mapped.subjectType).toBe("member");
    expect(mapped.subjectId).toBe("member-7");
    expect(mapped.teamId).toBe("team-9");
    expect(mapped.reportedBy).toBe("c1d2e3");
    expect(mapped.reportedAt).toBe("2026-04-08T10:30:00Z");
    expect(mapped.ttlSeconds).toBe(120);
    expect(mapped.source).toBe("cafebabe");
    expect(mapped.sourceIdentity).toBe("cafebabe");
    expect(mapped.sourceDisplayName).toBeNull();
    expect(mapped.overallStatus).toBe("Yellow");
    expect(mapped.capabilityStatus).toBe("Red");
  });

  it("preserves source identity when the API record also includes a display name", () => {
    const mapped = toEmergencyActionMessageRecord({
      callsign: "corvo",
      team_member_uid: "member-7",
      team_uid: "team-9",
      source: { rns_identity: "cafebabe", display_name: "Alpha Team" }
    });

    expect(mapped.source).toBe("Alpha Team");
    expect(mapped.sourceIdentity).toBe("cafebabe");
    expect(mapped.sourceDisplayName).toBe("Alpha Team");
  });

  it("maps UI EAM records to snake_case upsert payloads", () => {
    const payload = toEmergencyActionMessageUpsertPayload({
      callsign: "corvo",
      subjectType: "member",
      subjectId: "member-7",
      teamId: "team-9",
      reportedBy: "c1d2e3",
      reportedAt: "2026-04-08T10:30:00Z",
      securityStatus: "Green",
      securityCapability: "Yellow",
      preparednessStatus: "Red",
      medicalStatus: "Unknown",
      mobilityStatus: "Green",
      commsStatus: "Yellow",
      source: "cafebabe",
      overallStatus: "Red"
    });

    expect(payload).toEqual({
      callsign: "corvo",
      team_member_uid: "member-7",
      team_uid: "team-9",
      reported_by: "c1d2e3",
      reported_at: "2026-04-08T10:30:00Z",
      source: { rns_identity: "cafebabe" },
      security_status: "Green",
      capability_status: "Yellow",
      preparedness_status: "Red",
      medical_status: "Unknown",
      mobility_status: "Green",
      comms_status: "Yellow"
    });
    expect(payload).not.toHaveProperty("overall_status");
  });

  it("writes preserved source identity and display name back to the API payload", () => {
    const payload = toEmergencyActionMessageUpsertPayload({
      callsign: "corvo",
      subjectType: "member",
      subjectId: "member-7",
      teamId: "team-9",
      source: "Alpha Team",
      sourceIdentity: "cafebabe",
      sourceDisplayName: "Alpha Team"
    });

    expect(payload.source).toEqual({
      rns_identity: "cafebabe",
      display_name: "Alpha Team"
    });
  });
});
