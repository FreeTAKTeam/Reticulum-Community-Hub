import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useUsersStore } from "../src/stores/users";
import { useConnectionStore } from "../src/stores/connection";

const json = (body: unknown) => new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json" } });
const page = (items: unknown[], index: number, total: number) => ({
  items, page: index, per_page: 100, total, total_pages: Math.ceil(total / 100), has_next: index < Math.ceil(total / 100)
});
const identities = Array.from({ length: 203 }, (_, index) => ({ Identity: `identity-${index}` }));
const pathOf = (input: RequestInfo | URL) => new URL(String(input));

describe("bounded users directory", () => {
  beforeEach(() => { setActivePinia(createPinia()); });
  afterEach(() => { vi.unstubAllGlobals(); });

  it("loads every bounded page incrementally without truncating identities", async () => {
    const seen: string[] = [];
    const fetch = vi.fn((input: RequestInfo | URL) => {
      const url = pathOf(input);
      seen.push(url.pathname + url.search);
      if (url.pathname === "/Client") { return Promise.resolve(json(page([{ identity: "client" }], 1, 1))); }
      if (url.pathname === "/api/rem/peers") { return Promise.resolve(json({ items: [], effective_connected_mode: false })); }
      const index = Number(url.searchParams.get("page"));
      expect(url.searchParams.get("per_page")).toBe("100");
      return Promise.resolve(json(page(identities.slice((index - 1) * 100, index * 100), index, identities.length)));
    });
    vi.stubGlobal("fetch", fetch);
    const store = useUsersStore();
    await store.fetchUsers();
    expect(store.identities.map((entry) => entry.id)).toEqual(identities.map((entry) => entry.Identity));
    expect(store.identityTotal).toBe(203);
    expect(store.identitiesComplete).toBe(true);
    expect(store.loading).toBe(false);
    expect(seen).toContain("/Identities?page=3&per_page=100");
    expect(Object.values(store.errors)).toEqual([null, null, null]);
  });

  it("retains clients and REM peers when a legacy identity body exceeds 8 MiB", async () => {
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
    expect(store.errors.identities).toContain("8 MiB download limit");
    expect(store.identitiesComplete).toBe(false);
    expect(store.identities).toEqual([]);
  });

  it.each([
    { label: "malformed envelope", response: { page: 2, total: 203 } },
    { label: "unexpected legacy array", response: [] }
  ])("keeps successful pages visible and diagnoses a $label continuation", async ({ response }) => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = pathOf(input);
      if (url.pathname === "/Client") { return Promise.resolve(json([])); }
      if (url.pathname === "/api/rem/peers") { return Promise.resolve(json({ items: [] })); }
      if (url.searchParams.get("page") === "1") { return Promise.resolve(json(page(identities.slice(0, 100), 1, 203))); }
      return Promise.resolve(json(response));
    }));
    const store = useUsersStore();
    await store.fetchUsers();
    expect(store.identities).toHaveLength(100);
    expect(store.identityTotal).toBe(203);
    expect(store.identitiesComplete).toBe(false);
    expect(store.errors.identities).toContain("Invalid /Identities");
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
