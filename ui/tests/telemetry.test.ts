import { describe, expect, it } from "vitest";
import { deriveMarkers } from "../src/utils/telemetry";

describe("telemetry markers", () => {
  it("filters entries without location and maps fields", () => {
    const markers = deriveMarkers([
      {
        id: "1",
        identity_id: "deadbeef01",
        display_name: "Alpha",
        topic_id: "topic-1",
        created_at: "2024-01-01T00:00:00Z",
        location: { lat: 1, lon: 2 }
      },
      { id: "2", identity_id: "deadbeef02" }
    ]);

    expect(markers).toHaveLength(1);
    expect(markers[0].id).toBe("deadbeef01");
    expect(markers[0].name).toBe("Alpha");
    expect(markers[0].lat).toBe(1);
    expect(markers[0].lon).toBe(2);
  });

  it("skips operator marker telemetry entries", () => {
    const markers = deriveMarkers([
      {
        id: "1",
        identity_id: "f4c1d2e3",
        display_name: "Saddam",
        location: { lat: 1, lon: 2 },
        data: {
          custom: {
            marker: [{ object_type: "marker", event_type: "marker.created", symbol: "hostile" }, null]
          }
        }
      },
      {
        id: "2",
        identity_id: "deadbeef03",
        display_name: "Bravo",
        location: { lat: 3, lon: 4 },
        data: {
          telemetry_type: "person"
        }
      }
    ]);

    expect(markers).toHaveLength(1);
    expect(markers[0].id).toBe("deadbeef03");
    expect(markers[0].name).toBe("Bravo");
  });
});
