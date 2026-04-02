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
          ClientType: "rem",
          AnnounceCapabilities: ["r3akt", "emergencymessages"],
          RemMode: "connected",
          IsRemCapable: true
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
    expect(store.remConnectedMode).toBe(true);
    expect(store.remPeers[0].registered_mode).toBe("connected");
  });
});
