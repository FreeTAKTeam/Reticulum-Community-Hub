import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { createApp, nextTick } from "vue";
import { createPinia, setActivePinia } from "pinia";
import ReticulumConfigEditor from "../components/ReticulumConfigEditor.vue";
import ChatPage from "./ChatPage.vue";
import WebMapPage from "./WebMapPage.vue";
import DashboardPage from "./DashboardPage.vue";
import { get } from "../api/client";

const owners = vi.hoisted(() => ({ sockets: vi.fn(), removeMap: vi.fn() }));
vi.mock("../api/client", () => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), del: vi.fn(), getBlob: vi.fn() }));
vi.mock("../api/ws", () => ({ WsClient: class {
  constructor() { owners.sockets(); }
  connect() {} close() {} send() {}
} }));
vi.mock("../utils/mdi-icons", () => ({ loadMdiSvg: vi.fn().mockResolvedValue(null) }));
vi.mock("../components/OnlineHelpLauncher.vue", () => ({ default: { template: "<span />" } }));
vi.mock("maplibre-gl", () => ({ setWorkerUrl: vi.fn(), Map: class {
  on() {} off() {} resize() {} setLayoutProperty() {}
  getCanvas() { return document.createElement("canvas"); }
  getCenter() { return { lat: 0, lng: 0 }; }
  getZoom() { return 1; }
  doubleClickZoom = { enable() {} };
  dragPan = { enable() {} };
  remove() { owners.removeMap(); }
} }));

beforeEach(() => {
  vi.useFakeTimers(); vi.clearAllMocks(); localStorage.clear();
  vi.stubGlobal("matchMedia", () => ({ matches: true, addEventListener() {}, removeEventListener() {} }));
  vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} });
});
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

it.each([ChatPage, WebMapPage, DashboardPage, ReticulumConfigEditor])("does not start view resources after unmount during initial loading", async (page) => {
  let finish!: (value: unknown) => void;
  const pending = new Promise(resolve => { finish = resolve; });
  vi.mocked(get).mockReturnValue(pending);
  const pinia = createPinia(); setActivePinia(pinia);
  const host = document.createElement("div"); document.body.appendChild(host);
  const app = createApp(page).use(pinia); app.mount(host);
  await nextTick(); app.unmount();
  const timersAfterUnmount = vi.getTimerCount();
  finish([]);
  for (let i = 0; i < 40; i += 1) { await Promise.resolve(); }
  expect(owners.sockets).not.toHaveBeenCalled();
  expect(vi.getTimerCount()).toBe(timersAfterUnmount);
  if (page === WebMapPage) { expect(owners.removeMap).toHaveBeenCalledTimes(1); }
  host.remove();
});
