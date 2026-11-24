import { createPinia } from "pinia";
import { createApp, h, nextTick, type App } from "vue";
import { afterAll, afterEach, describe, expect, it, vi } from "vitest";
import EventFeedPanel from "../src/components/dashboard/EventFeedPanel.vue";
import type { EventEntry } from "../src/api/types";

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("../src/api/client", () => ({ get, post: vi.fn(), put: vi.fn(), del: vi.fn(), patch: vi.fn() }));

// Pin the clock to midday so "Today"/"Yesterday" grouping doesn't depend on when the suite runs.
vi.useFakeTimers({ toFake: ["Date"] });
vi.setSystemTime(new Date(2026, 10, 19, 12, 0, 0));
afterAll(() => vi.useRealTimers());

const RESCUE = "0f1e2d3c4b5a69788796a5b4c3d2e1f0";
const ALPHA = "a1b2c3d4e5f60718293a4b5c6d7e8f90";
const at = (minutesAgo: number) => new Date(Date.now() - minutesAgo * 60_000).toISOString();
const yesterdayNoon = () => { const date = new Date(); date.setDate(date.getDate() - 1); date.setHours(12, 0, 0, 0); return date.toISOString(); };
const events: EventEntry[] = [
  { id: "e1", category: "lxmf_command_diagnostic", message: "unsupported LXMF FIELD_COMMANDS (0x09)", level: "warning", created_at: at(1), metadata: { source: RESCUE } },
  { id: "e2", category: "durable_broker_handled", message: "inbound", created_at: at(1), metadata: { position: 9, source: RESCUE } },
  { id: "e3", category: "telemetry_request", message: "Telemetry collector snapshot served", created_at: at(2), metadata: { entry_count: 6, peer: ALPHA } },
  { id: "e4", category: "telemetry_request", message: "Telemetry collector snapshot served", created_at: at(3), metadata: { entry_count: 5, peer: ALPHA } },
  { id: "e5", category: "message_sent", message: "Message sent from hub", created_at: at(5), metadata: { destination: ALPHA, delivery_state: "sent", message_id: "7c3e91a0f4b2c9d8e7f6a5b4e18d" } },
  { id: "e6", category: "startup", message: "Hub started", created_at: yesterdayNoon(), metadata: {} }
];
const identities = new Map([[RESCUE, "Rescue Mobile"], [ALPHA, "Alpha Sideband"]]);

let app: App | undefined;
afterEach(() => { app?.unmount(); app = undefined; document.body.replaceChildren(); vi.clearAllMocks(); });

const mount = async () => {
  get.mockResolvedValue({ items: [], total: 0, page: 1, per_page: 50, total_pages: 0, has_next: false });
  const root = document.createElement("div");
  document.body.append(root);
  app = createApp({ render: () => h(EventFeedPanel, { events, identities }) }).use(createPinia());
  app.mount(root);
  await nextTick();
  return root;
};
const titles = (root: HTMLElement) => [...root.querySelectorAll(".event-feed__title")].map((node) => node.textContent?.replace(/\s+/g, " ").trim());
const click = async (element: Element | null | undefined) => { (element as HTMLElement).click(); await nextTick(); };
const tab = (root: HTMLElement, label: string) => [...root.querySelectorAll(".panel-tab")].find((node) => node.textContent?.trim() === label);

describe("event feed panel", () => {
  it("shows readable titles, hides transport steps and merges repeats", async () => {
    const root = await mount();
    expect(titles(root)).toEqual([
      "Unsupported command from Rescue Mobile",
      "Telemetry snapshot sent to Alpha Sideband ×2",
      "Message sent to Alpha Sideband",
      "Hub started"
    ]);
    expect(root.querySelector(".event-feed__footer")?.textContent).toContain("1 transport step hidden");
    expect([...root.querySelectorAll(".event-feed__day")].map((node) => node.textContent?.trim().split(" · ")[0])).toEqual(["Today", "Yesterday"]);

    await click([...root.querySelectorAll(".event-feed__link")].find((node) => node.textContent?.includes("Show transport internals")));
    expect(titles(root)).toContain("Inbound LXMF message processed");
  });

  it("filters by category tab and search", async () => {
    const root = await mount();
    await click(tab(root, "Errors"));
    expect(titles(root)).toEqual(["Unsupported command from Rescue Mobile"]);
    await click(tab(root, "All"));
    const search = root.querySelector<HTMLInputElement>("#event-feed-search")!;
    search.value = "alpha";
    search.dispatchEvent(new Event("input"));
    await nextTick();
    expect(titles(root)).toEqual(["Telemetry snapshot sent to Alpha Sideband ×2", "Message sent to Alpha Sideband"]);
  });

  it("expands a row into readable fields with names beside short addresses", async () => {
    const root = await mount();
    const row = [...root.querySelectorAll(".event-feed__item")].find((node) => node.textContent?.includes("Message sent to"))!;
    await click(row.querySelector(".event-feed__toggle"));
    const fields = [...row.querySelectorAll(".event-feed__fields dt")].map((node) => node.textContent?.trim());
    expect(fields).toEqual(["Destination", "Delivery state", "Message id"]);
    expect(row.querySelector(".event-feed__fields dd")?.textContent).toBe("Alpha Sideband a1b2c3d4…6d7e8f90");
    expect(row.querySelector(".event-feed__toggle")?.getAttribute("aria-expanded")).toBe("true");
    await click([...row.querySelectorAll(".event-feed__link")].find((node) => node.textContent?.includes("Show raw data")));
    expect(row.querySelector(".event-feed__raw")).not.toBeNull();
  });
});
