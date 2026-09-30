import { beforeEach, describe, expect, it, vi } from "vitest";
import { createApp, nextTick } from "vue";
import { createPinia, setActivePinia } from "pinia";
import ConnectPage from "./ConnectPage.vue";
import { get } from "../api/client";
import { useConnectionStore } from "../stores/connection";

const push = vi.hoisted(() => vi.fn());
vi.mock("vue-router", () => ({ useRouter: () => ({ push, currentRoute: { value: { query: {} } } }) }));
vi.mock("../api/client", () => ({ get: vi.fn() }));
describe("login lifecycle ownership", () => {
  beforeEach(() => { localStorage.clear(); vi.mocked(get).mockReset(); push.mockReset(); });
  it.each(["unmount", "change target"])("does not authenticate or redirect after %s", async (action) => {
    const pinia = createPinia(); setActivePinia(pinia);
    const connection = useConnectionStore();
    connection.baseUrl = "https://first.example";
    connection.authMode = "apiKey"; connection.apiKey = "fixture";
    let finish!: (value: unknown) => void;
    vi.mocked(get).mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
    const host = document.createElement("div"); document.body.appendChild(host);
    const app = createApp(ConnectPage).use(pinia); app.mount(host);
    const login = [...host.querySelectorAll("button")].find((button) => button.textContent?.includes("Log in"));
    expect(login).toBeDefined(); login?.click(); await nextTick();
    const signal = vi.mocked(get).mock.calls[0][1]?.signal;
    if (action === "unmount") { app.unmount(); } else { connection.baseUrl = "https://second.example"; }
    expect(signal?.aborted).toBe(true);
    finish({ status: "ok" });
    for (let i = 0; i < 10; i += 1) { await Promise.resolve(); }
    expect(connection.hasActiveAuthSession).toBe(false);
    expect(push).not.toHaveBeenCalled();
    if (action !== "unmount") { app.unmount(); }
    host.remove();
  });
});
