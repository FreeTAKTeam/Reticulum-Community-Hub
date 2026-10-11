import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
const { getMock } = vi.hoisted(() => ({ getMock: vi.fn() }));
vi.mock("../api/client", () => ({ get: getMock }));
import { useIdentityDirectoryStore } from "./identity-directory";
import { useConnectionStore } from "./connection";
const config = { identity_directory: { supported: true, page_size: 2, recent_hours: 7, lookup_max_entries: 3, lookup_concurrency: 2 } };
const query = { page: 1, view: "recent", search: "", clientType: "all", order: "last_seen_desc" } as const;
const page = (ids: string[], total = ids.length, number = 1, size = 2) => ({ items: ids.map((id) => ({ Identity: id, DisplayName: `Name ${id}`, Status: "active", IsBanned: false })), total, page: number, per_page: size, total_pages: Math.ceil(total / size), has_next: number < Math.ceil(total / size) });
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>((yes) => { resolve = yes; }); return { promise, resolve }; }
const settle = async () => { for (let i = 0; i < 12; i += 1) { await Promise.resolve(); } };
beforeEach(() => { localStorage.clear(); setActivePinia(createPinia()); getMock.mockReset(); });
describe("demand-driven identity pages", () => {
  it("uses configured page size, loads only one page and replaces it on navigation", async () => {
    getMock.mockResolvedValueOnce(config).mockResolvedValueOnce(page(["a", "b"], 15000)).mockResolvedValueOnce(page(["c", "d"], 15000, 2));
    const store = useIdentityDirectoryStore(); await store.fetchPage(query);
    expect(getMock).toHaveBeenCalledTimes(2); expect(store.items.map((entry) => entry.id)).toEqual(["a", "b"]);
    expect(store.total).toBe(15000); expect(getMock.mock.calls[1][0]).toContain("per_page=2");
    await store.fetchPage({ ...query, page: 2 }); expect(store.items.map((entry) => entry.id)).toEqual(["c", "d"]);
    expect(getMock).toHaveBeenCalledTimes(3);
  });
  it("rejects unsupported legacy arrays without retaining them", async () => {
    getMock.mockResolvedValueOnce(config).mockResolvedValueOnce([{ Identity: "a" }]);
    const store = useIdentityDirectoryStore(); await store.fetchPage(query);
    expect(store.unsupported).toBe(true); expect(store.items).toEqual([]); expect(store.error).toContain("legacy");
  });
  it("shows missing capability and malformed settings as distinct errors", async () => {
    getMock.mockResolvedValueOnce({ name: "Python" }); const store = useIdentityDirectoryStore(); await store.fetchPage(query);
    expect(store.unsupported).toBe(true); expect(getMock).toHaveBeenCalledTimes(1);
    store.invalidate(); getMock.mockResolvedValueOnce({ identity_directory: { ...config.identity_directory, lookup_concurrency: 0 } });
    await store.fetchPage(query); expect(store.unsupported).toBe(false); expect(store.error).toContain("configuration");
  });
  it("cancels stale same-backend searches, clears failures and retries", async () => {
    const old = deferred<unknown>(); getMock.mockResolvedValueOnce(config).mockReturnValueOnce(old.promise).mockResolvedValueOnce(page(["new"]));
    const store = useIdentityDirectoryStore(); const initial = store.fetchPage(query); await settle();
    const signal = getMock.mock.calls[1][1].signal as AbortSignal;
    await store.fetchPage({ ...query, search: "new" }); expect(signal.aborted).toBe(true);
    old.resolve(page(["old"])); await initial; expect(store.items[0].id).toBe("new");
    getMock.mockRejectedValueOnce(new Error("offline")); await store.fetchPage(query); expect(store.error).toBe("offline"); expect(store.items).toEqual([]);
    getMock.mockResolvedValueOnce(page(["retry"])); await store.fetchPage(query); expect(store.error).toBeNull(); expect(store.items[0].id).toBe("retry");
  });
  it("guards A-B-A responses and credentials changes", async () => {
    const old = deferred<unknown>(); const b = deferred<unknown>(); getMock.mockResolvedValueOnce(config).mockReturnValueOnce(old.promise);
    const store = useIdentityDirectoryStore(); const connection = useConnectionStore(); const url = connection.baseUrl;
    const aRequest = store.fetchPage(query); await settle(); connection.baseUrl = "https://b.example";
    getMock.mockResolvedValueOnce(config).mockReturnValueOnce(b.promise); const bRequest = store.fetchPage(query); await settle(); connection.baseUrl = url;
    getMock.mockResolvedValueOnce(config).mockResolvedValueOnce(page(["current-A"])); await store.fetchPage(query);
    old.resolve(page(["old-A"])); b.resolve(page(["B"])); await Promise.all([aRequest, bRequest]); expect(store.items[0].id).toBe("current-A");
    connection.apiKey = "changed"; expect(store.items).toEqual([]); expect(store.cache.size).toBe(0);
  });
});
describe("bounded scoped enrichment", () => {
  it("normalizes/deduplicates keys, caps cache and limits concurrent exact requests", async () => {
    const pending: ReturnType<typeof deferred<unknown>>[] = [];
    getMock.mockImplementation((path: string) => { if (path === "/api/v1/app/info") { return Promise.resolve(config); } const item = deferred<unknown>(); pending.push(item); return item.promise; });
    const store = useIdentityDirectoryStore(); const scope = store.register(); await store.setVisible(scope, [" A ", "a", "B", "C", "d"]);
    expect(pending).toHaveLength(2); expect(getMock.mock.calls[1][0]).toContain("identity=a"); expect(getMock.mock.calls[1][0]).toContain("per_page=1"); expect(getMock.mock.calls[1][0]).toContain("view=all");
    pending[0].resolve(page(["canonical-a"], 1, 1, 1)); pending[1].resolve(page(["b"], 1, 1, 1)); await settle(); expect(pending).toHaveLength(3);
    pending[2].resolve(page(["c"], 1, 1, 1)); await settle(); expect(store.cache.size).toBe(3); expect(store.lookup("A")?.id).toBe("canonical-a");
    await store.setVisible(scope, ["e"]); pending[3].resolve(page(["e"], 1, 1, 1)); await settle(); expect(store.cache.size).toBe(3); expect(store.lookup("e")?.display_name).toBe("Name e");
    store.unregister(scope);
  });
  it("aborts obsolete consumers, handles independent errors and invalidates mutation cache", async () => {
    const old = deferred<unknown>(); getMock.mockResolvedValueOnce(config).mockReturnValueOnce(old.promise).mockRejectedValueOnce(new Error("lookup failed"));
    const store = useIdentityDirectoryStore(); const scope = store.register(); await store.setVisible(scope, ["old"]); const signal = getMock.mock.calls[1][1].signal as AbortSignal;
    await store.setVisible(scope, ["new"]); expect(signal.aborted).toBe(true); await settle(); expect(store.lookupErrors.get("new")).toBe("lookup failed"); expect(store.items).toEqual([]);
    old.resolve(page(["old"], 1, 1, 1)); await settle(); expect(store.lookup("old")).toBeUndefined();
    store.unregister(scope); store.invalidate(); expect(store.lookupErrors.size).toBe(0); expect(store.cache.size).toBe(0);
  });
});
it("revalidates retained and negative/error cache only for visible IDs on refresh and revisit", async () => {
  let revision = 1;
  getMock.mockImplementation((path: string) => path === "/api/v1/app/info" ? Promise.resolve(config)
    : Promise.resolve({ ...page(["canonical"], 1, 1, 1), items: [{ Identity: "canonical", DisplayName: `Name ${revision}`, IsBanned: revision === 2 }] }));
  const store = useIdentityDirectoryStore(); const scope = store.register(); await store.setVisible(scope, ["key"]); await settle();
  expect(store.lookup("key")?.display_name).toBe("Name 1"); revision = 2; store.refreshVisible(); await settle();
  expect(store.lookup("key")?.display_name).toBe("Name 2"); expect(store.lookup("key")?.banned).toBe(true);
  store.unregister(scope); const next = store.register(); revision = 3; await store.setVisible(next, ["key"]); await settle();
  expect(store.lookup("key")?.display_name).toBe("Name 3"); expect(getMock.mock.calls.filter(([path]) => path.startsWith("/Identities"))).toHaveLength(3);
  getMock.mockRejectedValueOnce(new Error("offline")); store.refreshVisible(); await settle(); expect(store.lookupErrors.get("key")).toBe("offline");
  store.unregister(next); const final = store.register(); await store.setVisible(final, ["key"]); await settle(); expect(store.lookupErrors.has("key")).toBe(false); expect(store.lookup("key")?.display_name).toBe("Name 3");
});
it.each([{ page_size: 501 }, { lookup_max_entries: 10001 }, { lookup_concurrency: 17 }, { recent_hours: Infinity }])("rejects settings outside the server contract: %s", async (override) => {
  getMock.mockResolvedValueOnce({ identity_directory: { ...config.identity_directory, ...override } });
  const store = useIdentityDirectoryStore(); await store.fetchPage(query); expect(store.error).toContain("configuration"); expect(getMock).toHaveBeenCalledTimes(1);
});
it("retries a missing identity when its consumer revisits and discards a mutation-obsolete lookup", async () => {
  const old = deferred<unknown>();
  getMock.mockResolvedValueOnce(config).mockResolvedValueOnce(page([], 0, 1, 1));
  const store = useIdentityDirectoryStore(); const first = store.register(); await store.setVisible(first, ["missing"]); await settle();
  expect(store.cache.get("missing")).toBeNull(); store.unregister(first);
  getMock.mockReturnValueOnce(old.promise).mockResolvedValueOnce(page(["found"], 1, 1, 1));
  const second = store.register(); await store.setVisible(second, ["missing"]); const signal = getMock.mock.calls[2][1].signal as AbortSignal;
  store.invalidate(); expect(signal.aborted).toBe(true); await settle(); old.resolve(page(["stale"], 1, 1, 1)); await settle();
  expect(store.lookup("missing")?.id).toBe("found");
});
