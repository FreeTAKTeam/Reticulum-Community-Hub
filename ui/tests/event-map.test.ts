import { describe, expect, it } from "vitest";
import { eventFeatures, presentMapEvent } from "../src/utils/event-map";

describe("event map features", () => {
  it("maps MECP log entries with coordinates and skips the rest", () => {
    const mecp = (coordinates: unknown) => ({
      valid: true,
      category_label: "Supplies",
      severity_status: "green",
      extras: { coordinates }
    });
    const collection = eventFeatures([
      { entry_uid: "a", callsign: "R4", content: "MECP/1/S02 40.000000,-75.000000", mecp: mecp({ latitude: 40, longitude: -75 }) },
      { entry_uid: "b", content: "no position", mecp: mecp(null) },
      { entry_uid: "c", content: "plain", mecp: null },
      { entry_uid: "d", mecp: mecp({ latitude: 95, longitude: 0 }) }
    ]);
    expect(collection.features).toHaveLength(1);
    expect(collection.features[0].geometry.coordinates).toEqual([-75, 40]);
    expect(collection.features[0].properties).toMatchObject({ uid: "a", callsign: "R4", category: "Supplies", severity: "safety" });
  });

  it("prefers the event position from telemetry over MECP coordinates", () => {
    const collection = eventFeatures([
      { entry_uid: "t", content: "MECP/1/S02", latitude: 45.5, longitude: 9.2, mecp: { valid: true, extras: { coordinates: null } } },
      { entry_uid: "p", content: "plain text", latitude: 1, longitude: 2, mecp: null }
    ]);
    expect(collection.features.map((f) => f.geometry.coordinates)).toEqual([[9.2, 45.5], [2, 1]]);
    expect(collection.features[1].properties?.category).toBe("Event");
  });

  it("keys severity on the MECP severity number, then the colour status", () => {
    const at = { latitude: 1, longitude: 2 };
    const severities = eventFeatures([
      { entry_uid: "0", ...at, mecp: { valid: true, severity: 0, severity_status: "red" } },
      { entry_uid: "3", ...at, mecp: { valid: true, severity: 3, severity_status: "unknown" } },
      { entry_uid: "y", ...at, mecp: { valid: true, severity_status: "yellow" } },
      { entry_uid: "p", ...at, mecp: null }
    ]).features.map((feature) => feature.properties?.severity);
    expect(severities).toEqual(["mayday", "routine", "urgent", "none"]);
  });

  it("presents an MECP event for the map event window", () => {
    const view = presentMapEvent({
      entry_uid: "s01", callsign: "Rescue Mobile", content: "MECP/0/S01 45.4452,-63.6160 3pax #water",
      client_time: null, server_time: "2026-11-23T23:49:52.501Z", latitude: null, longitude: null,
      mission_uid: "sar-1", keywords: ["supplies", "r3akt:event-type:S", "r3akt:event-code:S01"],
      mecp: {
        valid: true, severity: 0, severity_status: "red", category_label: "Supplies", raw: "MECP/0/S01 45.4452,-63.6160 3pax #water",
        code_details: [{ code: "S01", label: "Need water" }],
        extras: { coordinates: { latitude: 45.4452, longitude: -63.616 }, pax: 3, eta_minutes: null, references: ["#water"] },
        warnings: []
      }
    });
    expect(view).toMatchObject({
      categoryLabel: "Supplies",
      severity: { key: "mayday", label: "Mayday" },
      headline: "S01 · Need water",
      lat: 45.4452,
      lon: -63.616,
      locationSource: "Coordinates in the MECP message",
      callsign: "Rescue Mobile",
      reportedAt: "",
      missionUid: "sar-1",
      keywords: ["supplies"],
      extras: ["3 pax", "#water"]
    });
  });

  it("presents a plain log entry with its own position, and skips entries without one", () => {
    expect(presentMapEvent({ entry_uid: "b", content: "Bridge out.", latitude: 45.4, longitude: -63.6, mecp: null, keywords: ["bridge"] }))
      .toMatchObject({ categoryLabel: "Log entry", severity: null, headline: "Bridge out.", rawCode: "", locationSource: "Position sent with the event" });
    expect(presentMapEvent({ entry_uid: "n", content: "no position", mecp: null })).toBeNull();
  });
});
