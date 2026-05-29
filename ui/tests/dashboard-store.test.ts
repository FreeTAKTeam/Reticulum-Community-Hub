import { beforeEach } from "vitest";
import { describe } from "vitest";
import { expect } from "vitest";
import { it } from "vitest";
import { vi } from "vitest";
import { createPinia } from "pinia";
import { setActivePinia } from "pinia";
import { useDashboardStore } from "../src/stores/dashboard";
import { resolveEventFeedMessage } from "../src/utils/event-feed";

const jsonResponse = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" }
  });

const requestUrl = (input: RequestInfo | URL): string => (typeof input === "string" ? input : input.toString());

const requestedPath = (fetchMock: ReturnType<typeof vi.fn>, path: string): boolean =>
  fetchMock.mock.calls.some(([input]) => requestUrl(input as RequestInfo | URL).endsWith(path));

describe("dashboard store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.restoreAllMocks();
  });

  it("counts active missions during refresh", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = requestUrl(input);
      if (url.endsWith("/Status")) {
        return Promise.resolve(jsonResponse({ clients: 4, topics: 2, subscribers: 7, telemetry: {} }));
      }
      if (url.endsWith("/api/r3akt/missions")) {
        return Promise.resolve(
          jsonResponse([
            { uid: "m-1", mission_status: "MISSION_ACTIVE" },
            { uid: "m-2", mission_status: "active" },
            { uid: "m-3", mission_status: "MISSION_PLANNED" }
          ])
        );
      }
      return Promise.resolve(jsonResponse({ detail: "not found" }, 404));
    });
    globalThis.fetch = fetchMock as typeof fetch;

    const store = useDashboardStore();
    await store.refresh();

    expect(store.status?.clients).toBe(4);
    expect(store.events).toHaveLength(0);
    expect(store.activeMissions).toBe(2);
    expect(requestedPath(fetchMock, "/Events")).toBe(false);
  });

  it("keeps dashboard refresh working when mission endpoint is unavailable", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = requestUrl(input);
      if (url.endsWith("/Status")) {
        return Promise.resolve(jsonResponse({ clients: 9, topics: 5, subscribers: 11, telemetry: {} }));
      }
      if (url.endsWith("/api/r3akt/missions")) {
        return Promise.resolve(jsonResponse({ detail: "missing" }, 404));
      }
      return Promise.resolve(jsonResponse({ detail: "not found" }, 404));
    });
    globalThis.fetch = fetchMock as typeof fetch;

    const store = useDashboardStore();
    await store.refresh();

    expect(store.status?.clients).toBe(9);
    expect(store.events).toHaveLength(0);
    expect(store.activeMissions).toBeNull();
    expect(requestedPath(fetchMock, "/Events")).toBe(false);
  });

  it("keeps dashboard refresh working when dev server fallback returns non-array payloads", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = requestUrl(input);
      if (url.endsWith("/Status")) {
        return Promise.resolve(
          new Response("<!DOCTYPE html><html></html>", {
            status: 200,
            headers: { "Content-Type": "text/html" }
          })
        );
      }
      if (url.endsWith("/api/r3akt/missions") || url.endsWith("/api/r3akt/team-members")) {
        return Promise.resolve(
          new Response("<!DOCTYPE html><html></html>", {
            status: 200,
            headers: { "Content-Type": "text/html" }
          })
        );
      }
      return Promise.resolve(jsonResponse({ detail: "not found" }, 404));
    });
    globalThis.fetch = fetchMock as typeof fetch;

    const store = useDashboardStore();
    await store.refresh();

    expect(store.events).toHaveLength(0);
    expect(store.activeMissions).toBe(0);
    expect(requestedPath(fetchMock, "/Events")).toBe(false);
  });

  it("uses client announce names when formatting event feed hashes", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = requestUrl(input);
      if (url.endsWith("/Status")) {
        return Promise.resolve(jsonResponse({ clients: 1, topics: 0, subscribers: 0, telemetry: {} }));
      }
      if (url.endsWith("/api/r3akt/missions") || url.endsWith("/api/r3akt/team-members")) {
        return Promise.resolve(jsonResponse([]));
      }
      if (url.endsWith("/Client")) {
        return Promise.resolve(
          jsonResponse([
            {
              identity: "fb4c70e20cfac047b899ca2f3671b50a",
              display_name: "R3AKT,EMergencyMessages,Telemetry;name=Pixelcorvo",
              announce_capabilities: ["R3AKT", "EMergencyMessages", "Telemetry", "name=pixelcorvo"]
            }
          ])
        );
      }
      if (url.endsWith("/Identities")) {
        return Promise.resolve(jsonResponse([]));
      }
      if (url.endsWith("/api/rem/peers")) {
        return Promise.resolve(jsonResponse({ effective_connected_mode: false, items: [] }));
      }
      return Promise.resolve(jsonResponse({ detail: "not found" }, 404));
    });
    globalThis.fetch = fetchMock as typeof fetch;

    const store = useDashboardStore();
    await store.refresh();
    store.pushEvent({
      timestamp: "2026-05-29T10:00:00Z",
      type: "message.delivery.retrying",
      message: "Retrying message delivery to fb4c70e20cfac047b899ca2f3671b50a",
      metadata: { Destination: "fb4c70e20cfac047b899ca2f3671b50a" }
    });

    expect(resolveEventFeedMessage(store.events[0], store.eventCallsignLookup)).toBe(
      "Retrying message delivery to Pixelcorvo"
    );
  });

  it("dedupes websocket replay and live duplicates by stable event identity", () => {
    const store = useDashboardStore();
    const event = {
      id: "evt-1",
      timestamp: "2026-05-29T12:00:00Z",
      type: "system.event",
      message: "Telemetry recorded",
      metadata: { source: "replay" }
    };

    store.pushEvent(event);
    store.pushEvent({ ...event, metadata: { source: "live" } });

    expect(store.events).toHaveLength(1);
    expect(store.events[0]?.message).toBe("Telemetry recorded");
  });

  it("sorts merged websocket events newest first", () => {
    const store = useDashboardStore();

    store.pushEvent({
      id: "older",
      timestamp: "2026-05-29T11:00:00Z",
      type: "system.event",
      message: "Older event"
    });
    store.pushEvent({
      id: "newer",
      timestamp: "2026-05-29T12:00:00Z",
      type: "system.event",
      message: "Newer event"
    });

    expect(store.events.map((event) => event.message)).toEqual(["Newer event", "Older event"]);
  });

  it("retains at most 200 websocket events", () => {
    const store = useDashboardStore();

    for (let index = 0; index < 205; index += 1) {
      store.pushEvent({
        id: `evt-${index}`,
        timestamp: new Date(Date.UTC(2026, 4, 29, 12, 0, index)).toISOString(),
        type: "system.event",
        message: `Event ${index}`
      });
    }

    expect(store.events).toHaveLength(200);
    expect(store.events[0]?.message).toBe("Event 204");
    expect(store.events.at(-1)?.message).toBe("Event 5");
  });
});
