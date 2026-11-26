import { createApp, h, nextTick, type App } from "vue";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Map as MapLibreMap } from "maplibre-gl";
import EventLayer from "../src/components/map/EventLayer.vue";

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("../src/api/client", () => ({ get, post: vi.fn(), put: vi.fn(), del: vi.fn(), patch: vi.fn() }));

let app: App | undefined;
afterEach(() => { app?.unmount(); app = undefined; vi.clearAllMocks(); });

describe("EventLayer", () => {
  it("draws events from the bare array the log-entries endpoint returns", async () => {
    get.mockResolvedValue([
      { entry_uid: "e1", content: "MECP/1/P06", latitude: 43.9672, longitude: -66.126367, mecp: { valid: true, severity_status: "yellow" } },
      { entry_uid: "e2", content: "no position", mecp: null }
    ]);
    const addSource = vi.fn();
    const map = {
      isStyleLoaded: () => true, getSource: () => undefined, getLayer: () => undefined,
      addSource, addLayer: vi.fn(), hasImage: () => false, addImage: vi.fn(), on: vi.fn(), off: vi.fn(), removeLayer: vi.fn(), removeSource: vi.fn()
    } as unknown as MapLibreMap;

    app = createApp({ render: () => h(EventLayer, { map }) });
    app.mount(document.createElement("div"));
    await vi.waitFor(() => expect(addSource).toHaveBeenCalled());
    await nextTick();

    const features = addSource.mock.calls.at(-1)?.[1].data.features;
    expect(features).toHaveLength(1);
    expect(features[0].geometry.coordinates).toEqual([-66.126367, 43.9672]);
  });

  it("adds the layer once the style is ready instead of skipping it while icons load", async () => {
    get.mockResolvedValue([{ entry_uid: "e1", content: "x", latitude: 43.9, longitude: -66.1, mecp: null }]);
    let styleReady = false;
    const idle: Array<() => void> = [];
    const addSource = vi.fn(() => { if (!styleReady) throw new Error("Style is not done loading."); });
    const map = {
      isStyleLoaded: () => false, getSource: () => undefined, getLayer: () => undefined, getStyle: () => ({ layers: [] }),
      addSource, addLayer: vi.fn(), hasImage: () => false, addImage: vi.fn(), on: vi.fn(), off: vi.fn(), once: (_: string, handler: () => void) => { idle.push(handler); },
      removeLayer: vi.fn(), removeSource: vi.fn(), moveLayer: vi.fn()
    } as unknown as MapLibreMap;

    app = createApp({ render: () => h(EventLayer, { map }) });
    app.mount(document.createElement("div"));
    await vi.waitFor(() => expect(idle).toHaveLength(1));
    styleReady = true;
    idle.shift()?.();
    expect(addSource).toHaveBeenLastCalledWith("rch-events", expect.objectContaining({ type: "geojson" }));
    expect((map.addLayer as ReturnType<typeof vi.fn>).mock.calls.map((call) => call[0].id)).toEqual(["rch-events-selected", "rch-events-point"]);
  });
});
