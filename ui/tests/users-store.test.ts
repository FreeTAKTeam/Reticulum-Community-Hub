import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useUsersStore } from "../src/stores/users";
import { useConnectionStore } from "../src/stores/connection";

const json = (body: unknown) => new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json" } });
const page = (items: unknown[], index: number, total: number) => ({
  items, page: index, per_page: 100, total, total_pages: Math.ceil(total / 100), has_next: index < Math.ceil(total / 100)
});
const clients = Array.from({ length: 203 }, (_, index) => ({ identity: `client-${index}` }));
const pathOf = (input: RequestInfo | URL) => new URL(String(input));

describe("bounded users directory", () => {
  beforeEach(() => { setActivePinia(createPinia()); });
  afterEach(() => { vi.unstubAllGlobals(); });

  it("loads the independent client roster without downloading identity history", async () => {
    const seen: string[] = [];
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = pathOf(input); seen.push(url.pathname + url.search);
      if (url.pathname === "/Client") {
        const index = Number(url.searchParams.get("page"));
        return Promise.resolve(json(page(clients.slice((index - 1) * 100, index * 100), index, clients.length)));
      }
      if (url.pathname === "/api/rem/peers") { return Promise.resolve(json({ items: [], effective_connected_mode: false })); }
      throw new Error("Unexpected historical directory request");
    }));
    const store = useUsersStore(); await store.fetchUsers();
    expect(store.clients.map((entry) => entry.id)).toEqual(clients.map((entry) => entry.identity));
    expect(seen).toContain("/Client?page=3&per_page=100");
    expect(seen.some((path) => path.startsWith("/Identities"))).toBe(false);
    expect(Object.values(store.errors)).toEqual([null, null]);
  });

  it("retains clients and REM peers without requesting an oversized legacy directory", async () => {
    const oversized = [{ Identity: "large", Metadata: { payload: "x".repeat(8 * 1024 * 1024) } }];
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = pathOf(input);
      if (url.pathname === "/Client") { return Promise.resolve(json([{ identity: "client" }])); }
      if (url.pathname === "/api/rem/peers") { return Promise.resolve(json({ items: [{ identity: "rem" }], effective_connected_mode: true })); }
      return Promise.resolve(json(oversized));
    }));
    const store = useUsersStore();
    await store.fetchUsers();
    expect(store.clients[0].id).toBe("client");
    expect(store.remPeers[0].identity).toBe("rem");
    expect(Object.values(store.errors)).toEqual([null, null]);
  });

  it.each([
    { label: "malformed envelope", response: { page: 2, total: 203 } },
    { label: "unexpected legacy array", response: [] }
  ])("keeps successful pages visible and diagnoses a $label continuation", async ({ response }) => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = pathOf(input);
      if (url.pathname === "/Client" && url.searchParams.get("page") === "1") { return Promise.resolve(json(page(clients.slice(0, 100), 1, 203))); }
      if (url.pathname === "/api/rem/peers") { return Promise.resolve(json({ items: [] })); }
      return Promise.resolve(json(response));
    }));
    const store = useUsersStore();
    await store.fetchUsers();
    expect(store.clients).toHaveLength(100);
    expect(store.errors.clients).toContain("Invalid /Client");
  });

  it("does not publish old pages or errors after connection credentials change", async () => {
    let complete!: (response: Response) => void;
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((resolve) => { complete = resolve; })));
    const store = useUsersStore();
    const pending = store.fetchClients();
    useConnectionStore().apiKey = "new-test-session";
    complete(json([{ identity: "old-backend" }]));
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
    expect(store.clients).toEqual([]);
    expect(store.errors.clients).toBeNull();
    expect(store.loading).toBe(false);
  });
});
