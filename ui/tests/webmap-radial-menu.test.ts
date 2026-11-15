import { createPinia } from "pinia";
import { createApp, nextTick, type App } from "vue";
import { afterEach, describe, expect, it, vi } from "vitest";
import WebMapPage from "../src/pages/WebMapPage.vue";

const { get, patch } = vi.hoisted(() => ({ get: vi.fn(), patch: vi.fn() }));
vi.mock("../src/api/client", () => ({ get, patch, post: vi.fn(), put: vi.fn(), del: vi.fn() }));
vi.mock("../src/api/ws", () => ({ WsClient: class { connect() {} close() {} send() {} } }));
vi.mock("../src/components/map/SensorGeometryLayer.vue", () => ({ default: { template: "<div />" } }));
vi.mock("maplibre-gl", () => ({
  setWorkerUrl: vi.fn(),
  Map: class {
    canvas = document.createElement("canvas");
    dragPan = { enable: vi.fn(), disable: vi.fn() };
    doubleClickZoom = { enable: vi.fn(), disable: vi.fn() };
    on() {}
    once() {}
    off() {}
    remove() {}
    getCanvas() { return this.canvas; }
    project() { return { x: 300, y: 300 }; }
  }
}));

let app: App | undefined;
afterEach(() => {
  app?.unmount();
  app = undefined;
  document.body.replaceChildren();
  localStorage.clear();
  vi.clearAllMocks();
});

const mountMap = async () => {
  get.mockImplementation(async (path: string) => {
    if (path === "/api/markers") {
      return [{ object_destination_hash: "marker-id", name: "Marker", position: { lat: 1, lon: 2 } }];
    }
    if (path === "/api/zones") {
      return [{ zone_id: "zone-id", name: "Zone", points: [{ lat: 0, lon: 0 }, { lat: 0, lon: 1 }, { lat: 1, lon: 1 }] }];
    }
    if (path === "/api/r3akt/missions") return [{ uid: "mission-1", mission_name: "Mission One" }];
    return [];
  });
  const root = document.createElement("div");
  document.body.append(root);
  app = createApp(WebMapPage).use(createPinia());
  const page = app.mount(root).$;
  await vi.waitFor(() => expect(page.setupState.markersStore.markerIndex.has("marker-id")).toBe(true));
  await vi.waitFor(() => expect(page.setupState.zonesStore.zoneIndex.has("zone-id")).toBe(true));
  return { page, root };
};

type Page = Awaited<ReturnType<typeof mountMap>>["page"];
const markerEvent = { features: [{ properties: { id: "marker-id" } }], point: { x: 300, y: 300 } };
const radialMenu = () => document.querySelector(".webmap-marker-radial-menu");
const hoverMarker = async (page: Page) => { page.setupState.handleOperatorMarkerHoverMove(markerEvent); await nextTick(); };
const leaveMarker = async (page: Page) => { page.setupState.handleOperatorMarkerHoverLeave(); await nextTick(); };
const clickEntry = async (label: string) => {
  const button = [...document.querySelectorAll<HTMLButtonElement>(".webmap-marker-radial-item")]
    .find((item) => item.textContent?.trim() === label);
  expect(button, `radial entry ${label}`).toBeDefined();
  button!.click();
  await nextTick();
};

describe("map radial menus", () => {
  it("does not reopen over the mission picker after Assign, so a mission can be chosen", async () => {
    const { page } = await mountMap();
    await hoverMarker(page);
    await clickEntry("Assign");
    await vi.waitFor(() => expect(page.setupState.markerAssignMissionUid).toBe("mission-1"));

    // The pointer is still over the marker on its way to the picker.
    await hoverMarker(page);
    expect(radialMenu()).toBeNull();
    expect(page.setupState.markerAssignOpen).toBe(true);

    // Even after leaving and coming back, the menu waits until the picker is closed.
    await leaveMarker(page);
    await hoverMarker(page);
    expect(radialMenu()).toBeNull();
    expect(page.setupState.markerAssignOpen).toBe(true);

    page.setupState.closeMarkerAssign();
    await hoverMarker(page);
    expect(radialMenu()).not.toBeNull();
  });

  it.each(["Send", "Edit", "Compass", "Delete"])(
    "keeps the menu closed after %s until the pointer leaves the marker and any dialog closes",
    async (label) => {
      const { page } = await mountMap();
      await hoverMarker(page);
      await clickEntry(label);
      await hoverMarker(page);
      expect(radialMenu()).toBeNull();

      await leaveMarker(page);
      page.setupState.markerShareId = null;
      if (page.setupState.markerRenameOpen) page.setupState.closeMarkerRename();
      await nextTick();
      if (label === "Delete") return;
      await hoverMarker(page);
      expect(radialMenu()).not.toBeNull();
    }
  );

  it("keeps the compass visible while the pointer stays on the marker", async () => {
    const { page } = await mountMap();
    await hoverMarker(page);
    await clickEntry("Compass");
    expect(page.setupState.markerCompassMarkerId).toBe("marker-id");
    await hoverMarker(page);
    expect(page.setupState.markerCompassMarkerId).toBe("marker-id");
  });

  it("does not reopen after closing the menu with its centre button while still on the marker", async () => {
    const { page } = await mountMap();
    await hoverMarker(page);
    document.querySelector<HTMLButtonElement>(".webmap-marker-radial-center")!.click();
    await nextTick();
    await hoverMarker(page);
    expect(radialMenu()).toBeNull();
  });

  it("keeps the zone mission picker open after zone Assign", async () => {
    const { page } = await mountMap();
    page.setupState.openHoverZoneRadialMenu("zone-id", { x: 300, y: 300 });
    await nextTick();
    await clickEntry("Assign");
    await vi.waitFor(() => expect(page.setupState.zoneAssignMissionUid).toBe("mission-1"));

    page.setupState.openHoverZoneRadialMenu("zone-id", { x: 310, y: 305 });
    await nextTick();
    expect(document.querySelector(".webmap-zone-radial-menu")).toBeNull();
    expect(page.setupState.zoneAssignOpen).toBe(true);

    page.setupState.handleZoneHoverLeave();
    page.setupState.closeZoneAssign();
    page.setupState.openHoverZoneRadialMenu("zone-id", { x: 300, y: 300 });
    await nextTick();
    expect(document.querySelector(".webmap-zone-radial-menu")).not.toBeNull();
  });

  it("keeps the zone rename prompt open after zone Edit", async () => {
    const { page } = await mountMap();
    page.setupState.openHoverZoneRadialMenu("zone-id", { x: 300, y: 300 });
    await nextTick();
    await clickEntry("Edit");
    expect(page.setupState.zonePromptOpen).toBe(true);
    page.setupState.openHoverZoneRadialMenu("zone-id", { x: 300, y: 300 });
    await nextTick();
    expect(document.querySelector(".webmap-zone-radial-menu")).toBeNull();
    expect(page.setupState.zonePromptOpen).toBe(true);
  });

  it("shows only the Close button at the centre of an open menu, with no Command Menu bubble under it", async () => {
    const { page } = await mountMap();
    page.setupState.hoveredOperatorMarkerId = "marker-id";
    page.setupState.hoveredOperatorMarkerPoint = { x: 300, y: 300 };
    await nextTick();
    expect(document.querySelector(".webmap-marker-reticle-core")?.textContent).toContain("Marker");

    await hoverMarker(page);
    expect(radialMenu()).not.toBeNull();
    expect(document.querySelector(".webmap-marker-reticle-core")).toBeNull();
    expect(document.body.textContent).not.toContain("Command Menu");
    expect(document.querySelector(".webmap-marker-radial-center")?.textContent?.trim()).toBe("Close");
  });
});
