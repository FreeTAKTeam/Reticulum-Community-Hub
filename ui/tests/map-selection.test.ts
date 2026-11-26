import { createPinia } from "pinia";
import { createApp, h, nextTick, type App } from "vue";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Map as MapLibreMap } from "maplibre-gl";
import MapSelection from "../src/components/map/MapSelection.vue";

const { del } = vi.hoisted(() => ({ del: vi.fn() }));
vi.mock("../src/api/client", () => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), del, patch: vi.fn() }));

const marker = { layer: { id: "operator-marker-layer" }, properties: { id: "mk1" }, geometry: { type: "Point", coordinates: [1, 2] } };
const event = { layer: { id: "rch-events-point" }, properties: { uid: "ev1" }, geometry: { type: "Point", coordinates: [3, 4] } };

let app: App | undefined;
afterEach(() => { app?.unmount(); app = undefined; document.body.replaceChildren(); vi.clearAllMocks(); });

const mount = () => {
  const container = document.createElement("div");
  const canvas = document.createElement("canvas");
  container.append(canvas);
  document.body.append(container);
  const behind = vi.fn();
  container.addEventListener("mousedown", behind);
  canvas.addEventListener("mousedown", behind);
  const map = {
    getCanvas: () => canvas, getLayer: () => ({}), getSource: () => undefined, addSource: vi.fn(), addLayer: vi.fn(),
    on: vi.fn(), off: vi.fn(), queryRenderedFeatures: vi.fn(() => [marker, event])
  };
  const deleted = vi.fn();
  const root = document.createElement("div");
  document.body.append(root);
  app = createApp({ render: () => h(MapSelection, { map: map as unknown as MapLibreMap, onDeleted: deleted }) }).use(createPinia());
  app.mount(root);
  const drag = async (from: [number, number], to: [number, number], shiftKey = true) => {
    canvas.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, shiftKey, button: 0, clientX: from[0], clientY: from[1] }));
    window.dispatchEvent(new MouseEvent("mousemove", { clientX: to[0], clientY: to[1] }));
    window.dispatchEvent(new MouseEvent("mouseup", { clientX: to[0], clientY: to[1] }));
    await nextTick();
  };
  return { map, drag, behind, deleted };
};

const bar = () => document.querySelector(".map-selection-bar");
const button = (label: string) => [...document.querySelectorAll("button")].find((node) => node.textContent?.trim() === label)!;

describe("map multi-select", () => {
  it("selects markers and events in a Shift+drag box without panning the map", async () => {
    const { map, drag, behind } = await mount();
    await drag([10, 10], [200, 150]);
    expect(behind).not.toHaveBeenCalled();
    expect(map.queryRenderedFeatures).toHaveBeenCalledWith([[10, 10], [200, 150]], { layers: ["operator-marker-layer", "rch-events-point"] });
    expect(bar()?.textContent).toContain("1 marker, 1 event selected");
  });

  it("leaves plain drags to the map", async () => {
    const { map, drag, behind } = await mount();
    await drag([10, 10], [200, 150], false);
    expect(behind).toHaveBeenCalled();
    expect(map.queryRenderedFeatures).not.toHaveBeenCalled();
    expect(bar()).toBeNull();
  });

  it("toggles one item with Shift+click and clears with Escape", async () => {
    const { map, drag } = await mount();
    map.queryRenderedFeatures.mockReturnValue([event]);
    await drag([50, 50], [50, 50]);
    expect(bar()?.textContent).toContain("1 event selected");
    await drag([50, 50], [51, 51]);
    expect(bar()).toBeNull();
    await drag([50, 50], [50, 50]);
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    await nextTick();
    expect(bar()).toBeNull();
  });

  it("deletes the selection after confirmation and keeps failures selected", async () => {
    const { drag, deleted } = await mount();
    await drag([10, 10], [200, 150]);
    del.mockImplementation(async (path: string) => {
      if (path === "/api/r3akt/log-entries/ev1") throw new Error("offline");
    });
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    button("Delete").click();
    await vi.waitFor(() => expect(deleted).toHaveBeenCalledWith({ markers: 1, events: 0 }));
    expect(del).toHaveBeenCalledWith("/api/markers/mk1");
    expect(del).toHaveBeenCalledWith("/api/r3akt/log-entries/ev1");
    await nextTick();
    expect(bar()?.textContent).toContain("1 event selected");
    confirm.mockRestore();
  });
});
