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
});
