import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useMarkersStore } from "../src/stores/markers";

const { getMock } = vi.hoisted(() => ({ getMock: vi.fn() }));
vi.mock("../src/api/client", () => ({ get: getMock }));

describe("marker expiry", () => {
  beforeEach(() => {
    localStorage.clear();
    setActivePinia(createPinia());
    getMock.mockReset();
  });

  it("keeps markers without an expiry visible and honors actual expiry dates", async () => {
    const marker = { position: { lat: 45.1, lon: -63.2 }, updated_at: "2023-11-14T22:13:22Z" };
    getMock.mockResolvedValue([
      { ...marker, object_destination_hash: "no-expiry" },
      { ...marker, object_destination_hash: "null-expiry", stale_at: null },
      { ...marker, object_destination_hash: "expired", stale_at: "2000-01-01T00:00:00Z" },
      { ...marker, object_destination_hash: "current", stale_at: "2999-01-01T00:00:00Z" }
    ]);
    const store = useMarkersStore();
    await store.fetchMarkers();
    expect(store.markers.filter((entry) => !entry.expired).map((entry) => entry.id))
      .toEqual(["no-expiry", "null-expiry", "current"]);
    expect(store.markerIndex.get("expired")?.expired).toBe(true);
  });
});
