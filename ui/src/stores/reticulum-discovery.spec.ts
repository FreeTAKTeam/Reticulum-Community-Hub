import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useReticulumDiscoveryStore } from "./reticulum-discovery";
import { useConnectionStore } from "./connection";
import { get } from "../api/client";
vi.mock("../api/client", () => ({ get: vi.fn() }));
function deferred() {
  let resolve!: (value: unknown) => void;
  const promise = new Promise(resolve_ => { resolve = resolve_; });
  return { promise, resolve };
}
beforeEach(() => { localStorage.clear(); setActivePinia(createPinia()); vi.resetAllMocks(); vi.useFakeTimers(); });
afterEach(() => { vi.useRealTimers(); });

it("shares a slow refresh across poll ticks and stops future requests on disposal", async () => {
  const response = deferred(); vi.mocked(get).mockReturnValue(response.promise);
  const store = useReticulumDiscoveryStore();
  const first = store.refresh(); store.startPolling();
  await vi.advanceTimersByTimeAsync(45_000);
  expect(get).toHaveBeenCalledTimes(2); expect(store.loading).toBe(true);
  store.stopPolling(); response.resolve({ runtime_active: true }); await first;
  await vi.advanceTimersByTimeAsync(30_000);
  expect(get).toHaveBeenCalledTimes(2); expect(store.polling).toBe(false); expect(store.loading).toBe(false);
});

it("keeps stale discovery responses from publishing or clearing a newer refresh", async () => {
  const old = deferred(); const current = deferred();
  vi.mocked(get).mockReturnValueOnce(old.promise).mockReturnValueOnce(old.promise)
    .mockReturnValueOnce(current.promise).mockReturnValueOnce(current.promise);
  const store = useReticulumDiscoveryStore(); const a = store.refresh();
  useConnectionStore().baseUrl = "https://hub-b.example"; const b = store.refresh();
  old.resolve({ runtime_active: true }); await expect(a).rejects.toMatchObject({ name: "AbortError" });
  expect(store.loading).toBe(true); expect(store.capabilities.runtime_active).toBe(false);
  current.resolve({ runtime_active: true }); await b;
  expect(store.capabilities.runtime_active).toBe(true); expect(store.loading).toBe(false);
});

it("holds a failed refresh until its slow sibling settles before admitting a retry", async () => {
  const slow = deferred(); const failure = new Error("capabilities failed");
  vi.mocked(get).mockRejectedValueOnce(failure).mockReturnValueOnce(slow.promise);
  const store = useReticulumDiscoveryStore(); const first = store.refresh();
  await Promise.resolve(); await Promise.resolve();
  const retryWhilePending = store.refresh();
  expect(get).toHaveBeenCalledTimes(2); expect(store.loading).toBe(true);
  slow.resolve({ runtime_active: false });
  await expect(first).rejects.toBe(failure); await expect(retryWhilePending).rejects.toBe(failure);
  expect(store.loading).toBe(false); expect(store.error).toBe("capabilities failed");
  vi.mocked(get).mockResolvedValue({ runtime_active: true });
  await store.refresh();
  expect(get).toHaveBeenCalledTimes(4); expect(store.discovery.runtime_active).toBe(true);
});
