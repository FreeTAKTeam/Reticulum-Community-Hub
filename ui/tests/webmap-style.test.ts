import { createPinia } from "pinia";
import { createApp, type App } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AJAXError } from "maplibre-gl";
import WebMapPage from "../src/pages/WebMapPage.vue";
import { useToastStore } from "../src/stores/toasts";

const { get, maps } = vi.hoisted(() => ({
  get: vi.fn(),
  maps: [] as Array<{ style: unknown; emitError: (error: Error) => void; setStyle: ReturnType<typeof vi.fn> }>
}));
vi.mock("../src/api/client", () => ({ get, patch: vi.fn(), post: vi.fn(), put: vi.fn(), del: vi.fn() }));
vi.mock("../src/api/ws", () => ({ WsClient: class { connect() {} close() {} send() {} } }));
vi.mock("../src/components/map/SensorGeometryLayer.vue", () => ({ default: { template: "<div />" } }));
vi.mock("maplibre-gl", () => ({
  setWorkerUrl: vi.fn(),
  AJAXError: class extends Error {
    constructor(_status: number, message: string, public url: string, _body: Blob) { super(message); }
  },
  Map: class {
    canvas = document.createElement("canvas");
    dragPan = { enable: vi.fn(), disable: vi.fn() };
    doubleClickZoom = { enable: vi.fn() };
    setStyle = vi.fn();
    style: unknown;
    private errorHandler?: (event: { error: Error }) => void;
    constructor(options: { style: unknown }) { this.style = options.style; maps.push(this); }
    on(type: string, handler: (event: { error: Error }) => void) { if (type === "error") this.errorHandler = handler; }
    emitError(error: Error) { this.errorHandler?.({ error }); }
    off() {}
    remove() {}
    getCanvas() { return this.canvas; }
  }
}));

const fiord = "https://tiles.openfreemap.org/styles/fiord";
let app: App | undefined;
beforeEach(() => { get.mockResolvedValue([]); });
afterEach(() => {
  app?.unmount();
  app = undefined;
  document.body.replaceChildren();
  localStorage.clear();
  maps.length = 0;
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
  vi.clearAllMocks();
});

const mount = () => {
  const root = document.createElement("div");
  document.body.append(root);
  const pinia = createPinia();
  app = createApp(WebMapPage).use(pinia);
  const page = app.mount(root).$;
  return { toasts: useToastStore(pinia), page };
};

describe("map style", () => {
  it.each([
    ["", "", fiord],
    ["https://example.test/rch.json", "https://example.test/legacy.json", "https://example.test/rch.json"],
    ["", "https://example.test/legacy.json", "https://example.test/legacy.json"]
  ])("selects the canonical override, legacy override, or Fiord", (canonical, legacy, expected) => {
    vi.stubEnv("VITE_RCH_MAP_STYLE_URL", canonical);
    vi.stubEnv("VITE_RTH_MAP_STYLE_URL", legacy);
    mount();
    expect(maps[0].style).toBe(expected);
  });

  it("falls back once when the default style request fails and reports the failure", () => {
    vi.stubEnv("VITE_RCH_MAP_STYLE_URL", "");
    vi.stubEnv("VITE_RTH_MAP_STYLE_URL", "");
    vi.spyOn(console, "warn").mockImplementation(() => {});
    const { toasts } = mount();
    const map = maps[0];
    const failure = new AJAXError(0, "offline", fiord, new Blob());
    map.emitError(failure);
    map.emitError(failure);
    expect(map.setStyle).toHaveBeenCalledOnce();
    expect(map.setStyle).toHaveBeenCalledWith(expect.objectContaining({ name: "RTH Vector Tactical" }), { diff: false });
    expect(toasts.messages.some((message) => message.tone === "warning")).toBe(true);
  });

  it("uses the Fiord-compatible font for operator and telemetry labels", () => {
    const { page } = mount();
    expect(page.setupState.buildMarkerLabelLayout()["text-font"]).toEqual(["Noto Sans Regular"]);
  });

  it.each(["", "/local/style.json"])("does not replace a style after a different map request fails", (custom) => {
    vi.stubEnv("VITE_RCH_MAP_STYLE_URL", custom);
    vi.stubEnv("VITE_RTH_MAP_STYLE_URL", "");
    vi.spyOn(console, "error").mockImplementation(() => {});
    mount();
    const map = maps[0];
    map.emitError(new AJAXError(404, "missing", "https://example.test/tile.pbf", new Blob()));
    expect(map.setStyle).not.toHaveBeenCalled();
    expect(console.error).toHaveBeenCalled();
  });

  it("does not silently replace an explicitly configured style", () => {
    vi.stubEnv("VITE_RCH_MAP_STYLE_URL", "/local/style.json");
    vi.spyOn(console, "error").mockImplementation(() => {});
    mount();
    maps[0].emitError(new AJAXError(404, "missing", "/local/style.json", new Blob()));
    expect(maps[0].setStyle).not.toHaveBeenCalled();
    expect(console.error).toHaveBeenCalled();
  });
});
