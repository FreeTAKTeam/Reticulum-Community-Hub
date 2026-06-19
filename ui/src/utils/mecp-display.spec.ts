import { describe, expect, it } from "vitest";

import { normalizeMecpDisplay } from "./mecp-display";

describe("normalizeMecpDisplay", () => {
  it("formats decoded MECP log metadata from the RCH API", () => {
    expect(
      normalizeMecpDisplay({
        valid: true,
        raw: "MECP/1/R03 T99 north gate",
        severity_label: "Urgent",
        severity_status: "yellow",
        category_label: "Response",
        code_details: [
          { code: "R03", label: "ETA [minutes]", known: true },
          { code: "T99", label: "T99", known: false }
        ],
        extras: {
          eta_minutes: 15,
          pax: 4,
          references: ["#A1"],
          coordinates: { latitude: 45.5017, longitude: -73.5673 }
        },
        details: "4pax 45.5017,-73.5673 #A1 15 @en north gate",
        warnings: ['Unknown MECP event code "T99".']
      })
    ).toEqual({
      raw: "MECP/1/R03 T99 north gate",
      severityLabel: "Urgent",
      severityStatus: "yellow",
      categoryLabel: "Response",
      codeLabels: ["R03 ETA [minutes]", "T99"],
      extraLabels: ["4 pax", "ETA 15 min", "#A1", "45.5017,-73.5673"],
      details: "4pax 45.5017,-73.5673 #A1 15 @en north gate",
      warnings: ['Unknown MECP event code "T99".']
    });
  });

  it("ignores invalid or absent decoded MECP metadata", () => {
    expect(normalizeMecpDisplay(null)).toBeNull();
    expect(normalizeMecpDisplay({ valid: false })).toBeNull();
  });

  it("falls back to MECP encoded content when the API has no decoded metadata", () => {
    expect(normalizeMecpDisplay(undefined, "MECP/0/C01 to me")).toEqual({
      raw: "MECP/0/C01 to me",
      severityLabel: "Mayday",
      severityStatus: "red",
      categoryLabel: "Coordination",
      codeLabels: ["C01 Send rescue"],
      extraLabels: [],
      details: "to me",
      warnings: []
    });
  });
});
