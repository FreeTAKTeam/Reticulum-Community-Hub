import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { afterEach, describe, expect, it, vi } from "vitest";
import ChatPage from "../src/pages/ChatPage.vue";
import { useConnectionStore } from "../src/stores/connection";
import { useChatStore } from "../src/stores/chat";

const { getMock, postMock, connect, close, send } = vi.hoisted(() => ({
  getMock: vi.fn(), postMock: vi.fn(), connect: vi.fn(), close: vi.fn(), send: vi.fn()
}));
vi.mock("../src/api/client", () => ({ get: getMock, post: postMock, getBlob: vi.fn() }));
vi.mock("../src/api/ws", () => ({ WsClient: class {
  connect = connect; close = close; send = send;
} }));

const settle = async () => { await nextTick(); await new Promise((resolve) => setTimeout(resolve, 0)); await nextTick(); };
const received = { MessageID: "received-test", Content: "Test1234", Direction: "inbound", Scope: "broadcast", State: "received" };

describe("independent chat initialization", () => {
  afterEach(() => { vi.clearAllMocks(); vi.unstubAllGlobals(); document.body.innerHTML = ""; });
  it("opens the stream immediately, displays received history and survives a roster failure without rendering errors", async () => {
    setActivePinia(createPinia());
    getMock.mockImplementation((path: string) => {
      if (path.startsWith("/Client")) { return Promise.reject(new Error("Response exceeds the 8 MiB download limit.")); }
      if (path.startsWith("/Chat/History")) { return Promise.resolve({ Messages: [received], NextCursor: null }); }
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
    useChatStore().upsertMessage({ message_id: "cached", created_at: new Date().toISOString(), scope: "broadcast", content: "Cached receipt" });
    getMock.mockImplementation((path: string) => Promise.resolve(path.startsWith("/Chat/History") ? { Messages: [received], NextCursor: null } : []));
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
    let resolve!: (messages: unknown) => void;
    getMock.mockImplementation(() => new Promise((done) => { resolve = done; }));
    const store = useChatStore();
    const pending = store.fetchMessages();
    store.upsertMessage({ message_id: "live", created_at: new Date().toISOString(), content: "Live receipt", scope: "broadcast" });
    resolve({ Messages: [received], NextCursor: null });
    await pending;
    expect(store.messages.map((entry) => entry.content)).toEqual(["Test1234", "Live receipt"]);
  });
  it("cancels a hashing continuation on logout and releases the page Send button", async () => {
    const pinia = createPinia(); setActivePinia(pinia);
    const connection = useConnectionStore(); connection.markAuthenticated();
    getMock.mockImplementation((path: string) => Promise.resolve(path.startsWith("/Chat/History") ? { Messages: [], NextCursor: null } : []));
    let finishDigest!: (buffer: ArrayBuffer) => void;
    const digest = vi.fn(() => new Promise<ArrayBuffer>((resolve) => { finishDigest = resolve; }));
    vi.stubGlobal("crypto", { subtle: { digest } });
    const root = document.createElement("div"); document.body.append(root);
    const app = createApp(ChatPage).use(pinia); app.mount(root); await settle();
    const input = root.querySelector('input[type="file"]') as HTMLInputElement;
    Object.defineProperty(input, "files", { value: [{ name: "attachment.txt", type: "text/plain", size: 3, arrayBuffer: () => Promise.resolve(new ArrayBuffer(3)) }] });
    input.dispatchEvent(new Event("change", { bubbles: true })); await settle();
    const button = [...root.querySelectorAll("button")].find((item) => item.textContent?.trim() === "Send")!;
    button.click(); await settle(); expect(digest).toHaveBeenCalled(); expect(button.disabled).toBe(true);
    connection.setAuthStatus("unauthenticated"); await settle(); expect(button.disabled).toBe(false);
    connection.markAuthenticated(); await settle();
    finishDigest(new ArrayBuffer(32)); await settle();
    expect(postMock).not.toHaveBeenCalled(); expect(button.disabled).toBe(false);
    app.unmount();
  });

});
