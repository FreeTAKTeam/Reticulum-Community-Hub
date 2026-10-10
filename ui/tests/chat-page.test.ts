import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { afterEach, describe, expect, it, vi } from "vitest";
import ChatPage from "../src/pages/ChatPage.vue";
import { useChatStore } from "../src/stores/chat";

const { getMock, connect, close, send } = vi.hoisted(() => ({
  getMock: vi.fn(), connect: vi.fn(), close: vi.fn(), send: vi.fn()
}));
vi.mock("../src/api/client", () => ({ get: getMock, post: vi.fn(), getBlob: vi.fn() }));
vi.mock("../src/api/ws", () => ({ WsClient: class {
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
