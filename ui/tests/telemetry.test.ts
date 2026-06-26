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

  it("preserves marker telemetry with its marker icon hint", () => {
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

    expect(markers).toHaveLength(2);
    expect(markers[0].id).toBe("f4c1d2e3");
    expect(markers[0].sourceType).toBe("operator-marker");
    expect(markers[0].iconKey).toBe("hostile");
    expect(markers[1].id).toBe("deadbeef03");
    expect(markers[1].name).toBe("Bravo");
    expect(markers[1].sourceType).toBe("telemetry");
    expect(markers[1].iconKey).toBeUndefined();
  });

  it("preserves server-recorded marker telemetry metadata with its marker icon hint", () => {
    const markers = deriveMarkers([
      {
        id: "1",
        identity_id: "marker-destination",
        display_name: "Hostile Marker",
        location: { lat: 1, lon: 2 },
        data: {
          custom: {
            type_label: "marker",
            metadata: {
              object_type: "marker",
              object_id: "marker-destination",
              event_type: "marker.created",
              symbol: "hostile"
            }
          }
        }
      },
      {
        id: "2",
        identity_id: "deadbeef04",
        display_name: "Charlie",
        location: { lat: 5, lon: 6 },
        data: {
          telemetry_type: "person"
        }
      }
    ]);

    expect(markers).toHaveLength(2);
    expect(markers[0].id).toBe("marker-destination");
    expect(markers[0].sourceType).toBe("operator-marker");
    expect(markers[0].iconKey).toBe("hostile");
    expect(markers[1].id).toBe("deadbeef04");
    expect(markers[1].sourceType).toBe("telemetry");
    expect(markers[1].iconKey).toBeUndefined();
  });
});
