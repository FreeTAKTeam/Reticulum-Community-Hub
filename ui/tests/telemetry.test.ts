import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useTelemetryStore } from "../src/stores/telemetry";
import { deriveMarkers } from "../src/utils/telemetry";

const { getMock } = vi.hoisted(() => ({ getMock: vi.fn() }));
vi.mock("../src/api/client", () => ({ get: getMock }));

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

describe("telemetry store", () => {
  const sample = (peer: string, timestamp: number) => ({
    peer_destination: peer,
    timestamp,
    telemetry: { location: { lat: timestamp, lon: 2 } }
  });

  beforeEach(() => {
    localStorage.clear();
    setActivePinia(createPinia());
    getMock.mockReset();
  });

  it("keeps one latest position per peer without evicting other peers on repeated updates", () => {
    const store = useTelemetryStore();
    store.applySnapshot([sample("abcdef02", 1), sample("abcdef01", 1)]);
    for (let timestamp = 2; timestamp <= 202; timestamp += 1) {
      store.applyUpdate(sample(" ABCDEF01 ", timestamp));
    }

    expect(store.entries).toHaveLength(2);
    expect(store.markers).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: "abcdef01", lat: 202 }),
      expect.objectContaining({ id: "abcdef02", lat: 1 })
    ]));
  });

  it("ignores older live positions even when the sample ID changes", () => {
    const store = useTelemetryStore();
    store.applyUpdate(sample("abcdef01", 20));
    store.applyUpdate(sample("abcdef01", 10));

    expect(store.entries).toHaveLength(1);
    expect(store.markers[0]).toMatchObject({ id: "abcdef01", lat: 20 });
  });

  it("uses the newest sample in snapshots regardless of their order or API shape", () => {
    const store = useTelemetryStore();
    store.applySnapshot([
      { id: "latest", identity_id: "ABCDEF01", created_at: new Date(20000).toISOString(), location: { lat: 20, lon: 2 } },
      sample("abcdef01", 10),
      sample("abcdef02", 10),
      sample("abcdef02", 30)
    ]);

    expect(store.entries).toHaveLength(2);
    expect(store.markers).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: "abcdef01", lat: 20 }),
      expect.objectContaining({ id: "abcdef02", lat: 30 })
    ]));
  });

  it("uses the newest sample from fetched telemetry", async () => {
    getMock.mockResolvedValue({ entries: [sample("abcdef01", 20), sample("abcdef01", 10)] });
    const store = useTelemetryStore();
    await store.fetchTelemetry(0);

    expect(store.entries).toHaveLength(1);
    expect(store.markers[0]).toMatchObject({ id: "abcdef01", lat: 20 });
  });

  it("keeps epoch-zero timestamps and accepts a replacement with the same timestamp", () => {
    const store = useTelemetryStore();
    store.applyUpdate(sample("abcdef01", 0));
    store.applyUpdate({ ...sample("abcdef01", 0), telemetry: { location: { lat: 2, lon: 3 } } });
    store.applyUpdate(sample("abcdef01", -1));

    expect(store.entries).toHaveLength(1);
    expect(store.markers[0]).toMatchObject({ lat: 2, lon: 3, updatedAt: "1970-01-01T00:00:00.000Z" });
  });

  it.each(["null", "[]", "42", "{\"identity_id\":42}"])("rejects malformed updates without changing the current positions: %s", (input) => {
    const store = useTelemetryStore();
    store.applySnapshot([sample("abcdef01", 10)]);
    const malformed = JSON.parse(input);

    expect(() => store.applyUpdate(malformed)).toThrow();
    expect(() => store.applySnapshot([sample("abcdef02", 20), malformed])).toThrow();
    expect(store.entries).toHaveLength(1);
    expect(store.markers[0]).toMatchObject({ id: "abcdef01", lat: 10 });
  });
});
