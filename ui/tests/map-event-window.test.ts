import { createPinia } from "pinia";
import { createApp, h, nextTick, type App } from "vue";
import { createMemoryHistory, createRouter } from "vue-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Map as MapLibreMap } from "maplibre-gl";
import EventLayer from "../src/components/map/EventLayer.vue";

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("../src/api/client", () => ({ get, post: vi.fn(), put: vi.fn(), del: vi.fn(), patch: vi.fn() }));

const MAYDAY = {
  entry_uid: "s01", callsign: "Rescue Mobile", content: "MECP/0/S01 45.4452,-63.6160 3pax #water",
  client_time: null, server_time: "2026-11-23T23:49:52.501Z", latitude: null, longitude: null,
  mission_uid: "sar-1", keywords: ["supplies", "r3akt:event-code:S01"],
  mecp: {
    valid: true, severity: 0, severity_status: "red", category_label: "Supplies", raw: "MECP/0/S01 45.4452,-63.6160 3pax #water",
    code_details: [{ code: "S01", label: "Need water" }],
    extras: { coordinates: { latitude: 45.4452, longitude: -63.616 }, pax: 3, references: ["#water"] }, warnings: []
  }
};

let app: App | undefined;
afterEach(() => { app?.unmount(); app = undefined; document.body.replaceChildren(); vi.clearAllMocks(); });

const mount = async () => {
  get.mockImplementation(async (path: string) => {
    if (path === "/api/r3akt/log-entries") return [MAYDAY];
    if (path === "/api/r3akt/missions") return [{ uid: "sar-1", mission_name: "SAR – Spruce Ridge" }];
    return [];
  });
  const handlers: Record<string, (event: unknown) => void> = {};
  const canvas = document.createElement("canvas");
  const map = {
    isStyleLoaded: () => true, getSource: () => undefined, getLayer: () => ({}), addSource: vi.fn(), addLayer: vi.fn(),
    on: (type: string, layer: string | ((event: unknown) => void), handler?: (event: unknown) => void) => {
      if (typeof layer === "string" && handler) handlers[`${type}:${layer}`] = handler;
    },
    off: vi.fn(), removeLayer: vi.fn(), removeSource: vi.fn(), setFilter: vi.fn(), getCanvas: () => canvas,
    getZoom: () => 9, flyTo: vi.fn()
  };
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: "/", component: { template: "<div />" } },
    { path: "/missions/:mission_uid/log-entries", name: "mission-domain-log-entries", component: { template: "<div />" } }
  ] });
  await router.push("/");
  const root = document.createElement("div");
  document.body.append(root);
  app = createApp({ render: () => h(EventLayer, { map: map as unknown as MapLibreMap }) }).use(createPinia()).use(router);
  app.mount(root);
  await vi.waitFor(() => expect(map.addSource).toHaveBeenCalled());
  return { map, root, router, click: async (uid: string) => {
    handlers["click:rch-events-point"]({ features: [{ properties: { uid } }] });
    await nextTick();
  } };
};

const dialog = () => document.querySelector("[role=dialog]");
const card = (title: string) => [...document.querySelectorAll(".map-event-card")].find((node) => node.querySelector("h4")?.textContent === title)!;
const button = (label: string) => [...document.querySelectorAll("button")].find((node) => node.textContent?.trim() === label)!;

describe("map event window", () => {
  it("opens a window instead of a raw popup, with the event laid out in cards", async () => {
    const { root, map, click } = await mount();
    expect(root.querySelector(".map-event-legend")?.textContent).toContain("Mayday");
    await click("s01");

    expect(dialog()?.getAttribute("aria-labelledby")).toBe(dialog()?.querySelector("h3")?.id);
    expect(dialog()?.querySelector("h3")?.textContent).toBe("Map Event: Supplies");
    expect(dialog()?.querySelector(".map-event-severity")?.textContent?.trim()).toBe("Mayday");
    expect(card("Report").textContent).toContain("S01 · Need water");
    expect(card("Report").textContent).toContain("MECP/0/S01");
    expect(card("Location").textContent).toContain("45.445200, -63.616000");
    expect(card("Location").textContent).toContain("Coordinates in the MECP message");
    expect(card("Sender").textContent).toContain("Rescue Mobile");
    await vi.waitFor(() => expect(card("Mission").textContent).toContain("SAR – Spruce Ridge"));
    expect(card("Mission").textContent).toContain("3 pax · #water");
    expect([...card("Mission").querySelectorAll(".map-event-keyword")].map((node) => node.textContent)).toEqual(["supplies"]);
    expect(map.setFilter).toHaveBeenLastCalledWith("rch-events-selected", ["==", ["get", "uid"], "s01"]);
  });

  it("centres the map at street level and closes", async () => {
    const { map, click } = await mount();
    await click("s01");
    button("Center map").click();
    await nextTick();
    expect(map.flyTo).toHaveBeenCalledWith({ center: [-63.616, 45.4452], zoom: 16 });
    expect(dialog()).toBeNull();
  });

  it("opens the mission log", async () => {
    const { router, click } = await mount();
    await click("s01");
    button("Open mission log").click();
    await vi.waitFor(() => expect(router.currentRoute.value.fullPath).toBe("/missions/sar-1/log-entries"));
    expect(dialog()).toBeNull();
  });
});
