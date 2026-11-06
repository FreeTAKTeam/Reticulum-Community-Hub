import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { WsHandler } from "../src/api/ws";
import ChatPage from "../src/pages/ChatPage.vue";
import { useChatStore } from "../src/stores/chat";

const { getMock, connect, close, send, streamHandlers } = vi.hoisted(() => ({
  getMock: vi.fn(), connect: vi.fn(), close: vi.fn(), send: vi.fn(), streamHandlers: [] as WsHandler[]
}));
vi.mock("../src/api/client", () => ({ get: getMock, post: vi.fn(), getBlob: vi.fn() }));
vi.mock("../src/api/ws", () => ({ WsClient: class {
  constructor(_path: string, handler: WsHandler) { streamHandlers.push(handler); }
  connect = connect; close = close; send = send;
} }));

const settle = async () => { await nextTick(); await new Promise((resolve) => setTimeout(resolve, 0)); await nextTick(); };
const received = { MessageID: "received-test", Content: "Test1234", Direction: "inbound", Scope: "broadcast", State: "received" };

describe("independent chat initialization", () => {
  afterEach(() => { vi.clearAllMocks(); document.body.innerHTML = ""; });
  it("opens the stream immediately, displays received history and survives a roster failure without rendering errors", async () => {
    setActivePinia(createPinia());
    getMock.mockImplementation((path: string) => {
      if (path.startsWith("/Client")) { return Promise.reject(new Error("Response exceeds the 8 MiB download limit.")); }
      if (path.startsWith("/Chat/Messages")) { return Promise.resolve([received]); }
      if (path === "/Topic") { return Promise.resolve([]); }
      return Promise.reject(new Error(`Unexpected GET ${path}`));
    });
    const errors: unknown[] = [];
    const root = document.createElement("div"); document.body.append(root);
    const app = createApp(ChatPage); app.use(createPinia());
    app.config.errorHandler = (error) => { errors.push(error); };
    app.mount(root);
    expect(connect).toHaveBeenCalledTimes(1);
    await settle();
    expect(root.textContent).toContain("Test1234");
    expect(root.textContent).toContain("Unable to load chat clients");
    expect(getMock.mock.calls.some(([path]) => String(path).startsWith("/Identities"))).toBe(false);
    expect(errors).toEqual([]);
    app.unmount(); expect(close).toHaveBeenCalledTimes(1);
  });

  it("renders cached messages when returning to Chat without an undefined-length crash", async () => {
    const pinia = createPinia(); setActivePinia(pinia);
    useChatStore().upsertMessage({ message_id: "cached", scope: "broadcast", content: "Cached receipt" });
    getMock.mockImplementation((path: string) => Promise.resolve(path.startsWith("/Chat/Messages") ? [received] : []));
    const errors: unknown[] = [];
    const root = document.createElement("div"); document.body.append(root);
    const app = createApp(ChatPage).use(pinia);
    app.config.errorHandler = (error) => { errors.push(error); };
    app.mount(root);
    await settle();
    app.unmount();
    expect(errors).toEqual([]);
  });

  it("retains live messages arriving while chat history is pending", async () => {
    setActivePinia(createPinia());
    let resolve!: (messages: unknown[]) => void;
    getMock.mockImplementation(() => new Promise((done) => { resolve = done; }));
    const store = useChatStore();
    const pending = store.fetchMessages();
    store.upsertMessage({ message_id: "live", content: "Live receipt", scope: "broadcast" });
    resolve([received]);
    await pending;
    expect(store.messages.map((entry) => entry.content)).toEqual(["Test1234", "Live receipt"]);
  });
});
it("enriches visible canonical/destination labels without treating discovery as online and refreshes moderation", async () => {
  const now = new Date().toISOString(); let banned = false;
  getMock.mockImplementation((path: string) => {
    if (path === "/api/v1/app/info") { return Promise.resolve({ identity_directory: { supported: true, page_size: 50, recent_hours: 24, lookup_max_entries: 500, lookup_concurrency: 4 } }); }
    if (path.startsWith("/Client")) { return Promise.resolve([{ identity: "announce-peer", last_seen: now }, { identity: "chat-peer", last_seen: now, last_chat_ts_ms: Date.now() }]); }
    if (path.startsWith("/Identities")) {
      const identity = new URLSearchParams(path.split("?")[1]).get("identity");
      return Promise.resolve({ items: [{ Identity: `canonical-${identity}`, DisplayName: `Label ${identity}`, Status: "active", RecentlyHeardAt: now, IsBanned: banned }], page: 1, per_page: 1, total: 1, total_pages: 1, has_next: false });
    }
    return Promise.resolve([]);
  });
  const pinia = createPinia(); setActivePinia(pinia); const root = document.createElement("div"); document.body.append(root);
  const app = createApp(ChatPage).use(pinia); app.mount(root); await settle(); await settle();
  const peers = [...root.querySelectorAll(".directory-item")];
  const announce = peers.find((entry) => entry.textContent?.includes("Label announce-peer"));
  const chat = peers.find((entry) => entry.textContent?.includes("Label chat-peer"));
  expect(announce).toBeDefined(); expect(announce?.querySelector(".presence-dot.online")).toBeNull(); expect(chat?.querySelector(".presence-dot.online")).not.toBeNull();
  expect(getMock.mock.calls.filter(([path]) => path.startsWith("/Identities")).every(([path]) => path.includes("identity=") && path.includes("per_page=1"))).toBe(true);
  banned = true; [...root.querySelectorAll("button")].find((button) => button.textContent?.trim() === "Refresh")?.click(); await settle(); await settle();
  expect(root.querySelectorAll(".presence-dot.online")).toHaveLength(0);
  app.unmount(); root.remove();
});


describe("server-projected hub broadcasts", () => {
  it("renders history and live inbound broadcasts once with their sender, preserves channel filters, and reloads history", async () => {
    const source = "columba-pixel";
    const hub = "hub-destination";
    const history = [
      { ...received, MessageID: "columba", Content: "Columba hub chat", Source: source, Destination: null, TopicID: "direct", DeliveryMetadata: { direction: "inbound", reticulumd_inbound: true } },
      { ...received, MessageID: "private", Content: "Private reply", Scope: "dm", Source: source, Destination: hub },
      { ...received, MessageID: "relay-1", Content: "Columba hub chat", Scope: "dm", Direction: "outbound", Source: null, Destination: "relay-peer-1", TopicID: null },
      { ...received, MessageID: "relay-2", Content: "Columba hub chat", Scope: "dm", Direction: "outbound", Source: null, Destination: "relay-peer-2", TopicID: null },
      { ...received, MessageID: "topic", Content: "Topic chat", Scope: "topic", Source: source, Destination: null, TopicID: "field", DeliveryMetadata: { direction: "inbound", reticulumd_inbound: true } }
    ];
    getMock.mockImplementation((path: string) => {
      if (path.startsWith("/Chat/Messages")) { return Promise.resolve(history); }
      if (path.startsWith("/Client")) { return Promise.resolve([{ identity: source, display_name: "Pixel" }]); }
      if (path === "/Topic") { return Promise.resolve([{ TopicID: "field", TopicName: "Field channel" }]); }
      return Promise.resolve([]);
    });
    const root = document.createElement("div"); document.body.append(root);
    const mount = () => { const app = createApp(ChatPage).use(createPinia()); app.mount(root); return app; };
    const app = mount();
    await settle();
    const bodies = () => [...root.querySelectorAll(".message-body")].map((entry) => entry.textContent);
    const click = async (selector: string, text: string) => {
      const button = [...root.querySelectorAll<HTMLButtonElement>(selector)].find((entry) => entry.textContent?.includes(text));
      expect(button).toBeDefined(); button!.click(); await settle();
    };
    expect(bodies()).toEqual(["Columba hub chat"]);
    expect(root.querySelector(".message-source")?.textContent).toBe("Pixel");
    const live = { ...received, MessageID: "ratspeak", Content: "Ratspeak hub chat", Source: "ratspeak-windows", Destination: null, TopicID: "direct", DeliveryMetadata: { direction: "inbound", reticulumd_inbound: true } };
    const emit = (entry: typeof live) => streamHandlers.at(-1)!({ type: "message.receive", ts: "2026-11-06T12:00:00Z", data: { entry } });
    emit(live); emit(live); await settle();
    expect(bodies()).toEqual(["Columba hub chat", "Ratspeak hub chat"]);
    expect([...root.querySelectorAll(".message-source")].map((entry) => entry.textContent)).toEqual(["Pixel", "ratspeak-windows"]);
    await click(".directory-item", "Pixel");
    expect(bodies()).toEqual(["Private reply"]);
    await click(".panel-tab", "Topics");
    await click(".directory-item", "Field channel");
    expect(bodies()).toEqual(["Topic chat"]);
    await click(".directory-item", "Broadcast");
    history.unshift(live);
    app.unmount();
    const reloaded = mount(); await settle();
    expect(bodies()).toEqual(["Columba hub chat", "Ratspeak hub chat"]);
    expect(root.querySelectorAll(".message-card")).toHaveLength(2);
    reloaded.unmount(); root.remove();
  });
});
