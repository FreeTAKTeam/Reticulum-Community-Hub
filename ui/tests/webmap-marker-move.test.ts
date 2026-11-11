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
    doubleClickZoom = { enable: vi.fn() };
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

describe("map marker movement", () => {
  it("keeps hover menus closed while a marker is armed or dragging, then allows them again", async () => {
    get.mockImplementation(async (path: string) => path === "/api/markers" ? [{
      object_destination_hash: "marker-id", name: "Marker", position: { lat: 1, lon: 2 }
    }] : []);
    patch.mockResolvedValue({});
    const root = document.createElement("div");
    document.body.append(root);
    app = createApp(WebMapPage).use(createPinia());
    const page = app.mount(root).$;
    await vi.waitFor(() => expect(page.setupState.markersStore.markerIndex.has("marker-id")).toBe(true));

    const markerEvent = { features: [{ properties: { id: "marker-id" } }], point: { x: 300, y: 300 } };
    page.setupState.handleOperatorMarkerHoverMove(markerEvent);
    await nextTick();
    const move = [...root.querySelectorAll(".webmap-marker-radial-item")]
      .find((button) => button.textContent?.includes("Move"));
    expect(move).toBeDefined();
    (move as HTMLButtonElement).click();
    await nextTick();

    page.setupState.handleOperatorMarkerHoverMove(markerEvent);
    await nextTick();
    expect(root.querySelector(".webmap-marker-radial-menu")).toBeNull();
    page.setupState.handleTelemetryMarkerHoverMove({ ...markerEvent, features: [{ properties: { id: "person-id" } }] });
    await nextTick();
    expect(root.querySelector(".webmap-marker-radial-menu")).toBeNull();
    page.setupState.openHoverZoneRadialMenu("zone-id", { x: 300, y: 300 });
    await nextTick();
    expect(root.querySelector(".webmap-marker-radial-menu")).toBeNull();

    page.setupState.startMarkerDrag({ ...markerEvent, originalEvent: { button: 0, preventDefault() {} }, preventDefault() {} });
    page.setupState.handleMarkerDrag({ lngLat: { lat: 3, lng: 4 } });
    page.setupState.handleTelemetryMarkerHoverMove({ ...markerEvent, features: [{ properties: { id: "person-id" } }] });
    await nextTick();
    expect(root.querySelector(".webmap-marker-radial-menu")).toBeNull();
    page.setupState.openHoverZoneRadialMenu("zone-id", { x: 300, y: 300 });
    await nextTick();
    expect(root.querySelector(".webmap-marker-radial-menu")).toBeNull();
    page.setupState.finishMarkerDrag();
    await vi.waitFor(() => expect(patch).toHaveBeenCalledWith("/api/markers/marker-id/position", { lat: 3, lon: 4 }));

    page.setupState.handleOperatorMarkerHoverMove(markerEvent);
    await nextTick();
    expect(root.querySelector(".webmap-marker-radial-menu")).not.toBeNull();
  });
});
