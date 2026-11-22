import { describe, expect, it } from "vitest";
import { eventFeatures } from "../src/utils/event-map";

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
    expect(collection.features[0].properties).toMatchObject({ uid: "a", callsign: "R4", category: "Supplies", severity: "green" });
  });

  it("prefers the event position from telemetry over MECP coordinates", () => {
    const collection = eventFeatures([
      { entry_uid: "t", content: "MECP/1/S02", latitude: 45.5, longitude: 9.2, mecp: { valid: true, extras: { coordinates: null } } },
      { entry_uid: "p", content: "plain text", latitude: 1, longitude: 2, mecp: null }
    ]);
    expect(collection.features.map((f) => f.geometry.coordinates)).toEqual([[9.2, 45.5], [2, 1]]);
    expect(collection.features[1].properties?.category).toBe("Event");
  });
});
