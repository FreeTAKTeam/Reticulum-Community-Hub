import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useZonesStore } from "../src/stores/zones";

describe("zones store", () => {
  const now = "2026-02-12T12:00:00.000Z";

  beforeEach(() => {
    setActivePinia(createPinia());
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("fetches zones", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify([
          {
            zone_id: "zone-1",
            name: "Alpha",
            points: [
              { lat: 1, lon: 2 },
              { lat: 1.1, lon: 2 },
              { lat: 1.1, lon: 2.1 },
            ],
            created_at: now,
            updated_at: now,
          },
        ]),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }
      )
    ) as any;

    const store = useZonesStore();
    await store.fetchZones();

    expect(store.zones).toHaveLength(1);
    expect(store.zones[0].id).toBe("zone-1");
    expect(store.zones[0].name).toBe("Alpha");
  });

  it("creates, updates, and deletes zones", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const requestUrl = typeof input === "string" ? input : input.toString();
      const pathname = new URL(requestUrl).pathname;
      const method = init?.method ?? "GET";

      if (pathname === "/api/zones" && method === "POST") {
        return new Response(JSON.stringify({ zone_id: "zone-2", created_at: now }), {
          status: 201,
          headers: { "Content-Type": "application/json" },
        });
      }

      if (pathname === "/api/zones/zone-2" && method === "PATCH") {
        return new Response(JSON.stringify({ status: "ok", updated_at: now }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      if (pathname === "/api/zones/zone-2" && method === "DELETE") {
        return new Response(JSON.stringify({ status: "ok", deleted_at: now }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      return new Response(JSON.stringify({ detail: "not found" }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      });
    });
    globalThis.fetch = fetchMock as any;

    const store = useZonesStore();
    await store.createZone({
      name: "Bravo",
      points: [
        { lat: 1, lon: 2 },
        { lat: 1.1, lon: 2 },
        { lat: 1.1, lon: 2.1 },
      ],
    });

    expect(store.zones).toHaveLength(1);
    expect(store.zones[0].id).toBe("zone-2");

    await store.updateZone("zone-2", { name: "Bravo Updated" });
    expect(store.zones[0].name).toBe("Bravo Updated");

    await store.deleteZone("zone-2");
    expect(store.zones).toHaveLength(0);
  });
});
