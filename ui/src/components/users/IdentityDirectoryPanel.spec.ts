import { createApp, nextTick } from "vue";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
const { getMock } = vi.hoisted(() => ({ getMock: vi.fn() }));
vi.mock("../../api/client", () => ({ get: getMock }));
import IdentityDirectoryPanel from "./IdentityDirectoryPanel.vue";
import { useConnectionStore } from "../../stores/connection";
const config = { identity_directory: { supported: true, page_size: 2, recent_hours: 7, lookup_max_entries: 3, lookup_concurrency: 1 } };
const response = (number = 1) => ({ items: [{ Identity: `identity-${number}`, DisplayName: `Person ${number}`, Status: "active", IsBanned: true, Metadata: { voice: { destination_hash: "voice-destination" } } }, { Identity: `second-${number}` }], total: 10, page: number, per_page: 2, total_pages: 5, has_next: number < 5 });
const settle = async () => { for (let i = 0; i < 8; i += 1) { await Promise.resolve(); await nextTick(); } };
let cleanup: (() => void) | undefined;
beforeEach(() => { localStorage.clear(); vi.useFakeTimers(); getMock.mockReset(); });
afterEach(() => { cleanup?.(); vi.useRealTimers(); });
const mount = () => {
  const pinia = createPinia(); setActivePinia(pinia);
  const node = document.createElement("div"); document.body.append(node);
  const action = vi.fn(); const join = vi.fn();
  const app = createApp(IdentityDirectoryPanel, { joinedIds: new Set(["identity-1"]), onAction: action, onJoin: join }); app.use(pinia); app.mount(node);
  cleanup = () => { app.unmount(); node.remove(); };
  return { node, action, join };
};
it("renders server totals/recency, preserves moderation/voice/join actions and requests explicit pages", async () => {
  getMock.mockResolvedValueOnce(config).mockResolvedValueOnce(response()).mockResolvedValueOnce(response(2));
  const { node, action } = mount(); await settle();
  expect(getMock).toHaveBeenCalledTimes(2); expect(node.textContent).toContain("7 hours"); expect(node.textContent).toContain("10 matching"); expect(node.textContent).toContain("Voice"); expect(node.textContent).toContain("Banned");
  const joined = [...node.querySelectorAll("button")].find((button) => button.textContent?.trim() === "Joined"); expect(joined?.disabled).toBe(true);
  [...node.querySelectorAll("button")].find((button) => button.textContent?.trim() === "Ban")?.click(); expect(action).toHaveBeenCalledWith("identity-1", "Ban");
  [...node.querySelectorAll("button")].find((button) => button.textContent?.trim() === "Next")?.click(); await settle();
  expect(getMock.mock.calls[2][0]).toContain("page=2"); expect(node.textContent).toContain("Person 2"); expect(node.textContent).not.toContain("Person 1");
});
it("debounces search after page navigation and requests all history/filter/order from the backend", async () => {
  getMock.mockImplementation((path: string) => {
    if (path === "/api/v1/app/info") { return Promise.resolve(config); }
    const params = new URLSearchParams(path.split("?")[1]); return Promise.resolve(response(Number(params.get("page"))));
  });
  const { node } = mount(); await settle(); [...node.querySelectorAll("button")].find((button) => button.textContent?.trim() === "Next")?.click(); await settle();
  const input = node.querySelector("input")!; input.value = "old"; input.dispatchEvent(new Event("input")); input.value = "older"; input.dispatchEvent(new Event("input"));
  await settle(); expect(getMock).toHaveBeenCalledTimes(3);
  await vi.advanceTimersByTimeAsync(250); await settle(); expect(getMock).toHaveBeenCalledTimes(4); expect(getMock.mock.calls[3][0]).toContain("search=older"); expect(getMock.mock.calls[3][0]).toContain("page=1");
  const selects = node.querySelectorAll("select"); selects[0].value = "all"; selects[0].dispatchEvent(new Event("change")); selects[1].value = "rem"; selects[1].dispatchEvent(new Event("change")); selects[2].value = "identity_asc"; selects[2].dispatchEvent(new Event("change"));
  await vi.advanceTimersByTimeAsync(250); await settle(); const url = getMock.mock.calls.at(-1)?.[0]; expect(url).toContain("view=all"); expect(url).toContain("client_type=rem"); expect(url).toContain("order=identity_asc");
});
it("shows unsupported state, refreshes only one active directory page and reloads after backend switches", async () => {
  getMock.mockResolvedValueOnce({ name: "legacy" }); const { node } = mount(); await settle(); expect(node.textContent).toContain("does not support"); expect(getMock).toHaveBeenCalledTimes(1);
  getMock.mockResolvedValueOnce(config).mockResolvedValueOnce(response()); [...node.querySelectorAll("button")].find((button) => button.textContent?.trim() === "Refresh")?.click(); await settle(); expect(node.textContent).toContain("Person 1");
  getMock.mockResolvedValueOnce(config).mockResolvedValueOnce(response()); useConnectionStore().baseUrl = "https://other.example"; await settle(); expect(getMock.mock.calls.filter(([url]) => url.startsWith("/Identities"))).toHaveLength(2);
});
