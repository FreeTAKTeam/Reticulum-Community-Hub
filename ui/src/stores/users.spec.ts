// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

const { getMock, postMock, putMock } = vi.hoisted(() => ({
  getMock: vi.fn(),
  postMock: vi.fn(),
  putMock: vi.fn()
}));

vi.mock("../api/client", () => ({
  get: getMock,
  post: postMock,
  put: putMock
}));

import { useUsersStore } from "./users";

describe("users store REM registry mapping", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    getMock.mockReset();
    postMock.mockReset();
    putMock.mockReset();
  });

  it("maps backend supplied REM classification and peer registry without local inference", async () => {
    getMock
      .mockResolvedValueOnce([
        {
          identity: "rem-1",
          last_seen: "2026-04-02T12:00:00Z",
          display_name: "REM Alpha",
          client_type: "rem",
          announce_capabilities: ["r3akt", "emergencymessages"],
          rem_mode: "connected",
          is_rem_capable: true
        },
        {
          identity: "generic-1",
          last_seen: "2026-04-02T12:00:00Z",
          display_name: "Generic Bravo",
          client_type: "generic_lxmf",
          announce_capabilities: ["telemetry"],
          rem_mode: null,
          is_rem_capable: false
        }
      ])
      .mockResolvedValueOnce([
        {
          Identity: "rem-1",
          DisplayName: "REM Alpha",
          Status: "active",
          LastSeen: "2026-04-02T12:00:00Z",
          ClientType: "rem",
          AnnounceCapabilities: ["r3akt", "emergencymessages"],
          RemMode: "connected",
          IsRemCapable: true,
          IsAnnounced: true,
          AnnounceDestinationHash: "rem-destination",
          AnnounceSource: "FTSRET",
          AnnounceFirstSeen: "2026-04-02T11:59:00Z",
          AnnounceLastSeen: "2026-04-02T12:01:00Z"
        }
      ])
      .mockResolvedValueOnce({
        effective_connected_mode: true,
        items: [
          {
            identity: "rem-1",
            destination_hash: "rem-1",
            display_name: "REM Alpha",
            announce_capabilities: ["r3akt", "emergencymessages"],
            client_type: "rem",
            registered_mode: "connected",
            status: "active"
          }
        ]
      });

    const store = useUsersStore();
    await store.fetchUsers();

    expect(store.clients[0].client_type).toBe("rem");
    expect(store.clients[0].rem_mode).toBe("connected");
    expect(store.clients[1].client_type).toBe("generic_lxmf");
    expect(store.clients[1].rem_mode).toBeUndefined();
    expect(store.identities[0].is_rem_capable).toBe(true);
    expect(store.identities[0].is_announced).toBe(true);
    expect(store.identities[0].announce_source).toBe("FTSRET");
    expect(store.identities[0].announce_destination_hash).toBe("rem-destination");
    expect(store.identities[0].last_seen).toBe("2026-04-02T12:01:00Z");
    expect(store.remConnectedMode).toBe(true);
    expect(store.remPeers[0].registered_mode).toBe("connected");
  });
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

import { useConnectionStore } from "./connection";

it("shares simultaneous roster reads and retries after failure", async () => {
  localStorage.clear(); setActivePinia(createPinia()); getMock.mockReset();
  const first = deferred<unknown[]>();
  getMock.mockReturnValueOnce(first.promise);
  const store = useUsersStore();
  const a = store.fetchUsers(); const b = store.fetchUsers();
  expect(getMock).toHaveBeenCalledTimes(1);
  const failure = new Error("offline"); first.reject(failure);
  await expect(a).rejects.toBe(failure); await expect(b).rejects.toBe(failure);
  expect(store.loading).toBe(false);
  getMock.mockResolvedValueOnce([]).mockResolvedValueOnce([]).mockResolvedValueOnce({ items: [] });
  await store.fetchUsers();
  expect(getMock).toHaveBeenCalledTimes(4);
});

it("isolates A to B to A requests and stale finally blocks", async () => {
  localStorage.clear(); setActivePinia(createPinia()); getMock.mockReset();
  const original = deferred<unknown[]>(); const hubB = deferred<unknown[]>(); const newA = deferred<unknown[]>();
  getMock.mockReturnValueOnce(original.promise).mockReturnValueOnce(hubB.promise).mockReturnValueOnce(newA.promise);
  const connection = useConnectionStore(); const originalUrl = connection.baseUrl;
  const store = useUsersStore(); const a = store.fetchUsers();
  connection.baseUrl = "https://hub-b.example";
  const b = store.fetchUsers();
  original.resolve([{ identity: "old-A" }]);
  await expect(a).rejects.toMatchObject({ name: "AbortError" });
  expect(store.loading).toBe(true); expect(store.clients).toEqual([]);
  connection.baseUrl = originalUrl;
  const newRequest = store.fetchUsers();
  hubB.reject(new Error("B offline")); await expect(b).rejects.toThrow("B offline");
  expect(store.loading).toBe(true);
  getMock.mockResolvedValueOnce([{ Identity: "new-A" }]).mockResolvedValueOnce({ items: [] });
  newA.resolve([{ identity: "new-A" }]); await newRequest;
  expect(store.clients[0].id).toBe("new-A"); expect(store.loading).toBe(false);
});
