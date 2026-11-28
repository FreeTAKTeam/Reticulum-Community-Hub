import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useChatStore } from "./chat";

vi.mock("../api/client", () => ({
  get: vi.fn(),
  post: vi.fn()
}));

import { get } from "../api/client";

const mockedGet = vi.mocked(get);

describe("chat store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    mockedGet.mockReset();
  });

  it("loads wrapped chat message lists from compatibility responses", async () => {
    mockedGet.mockResolvedValue({
      Messages: [
        {
          MessageID: "2a2892b3227b427487308d53712dd163",
          Direction: "outbound",
          Scope: "broadcast",
          State: "propagated",
          Content: "broadcast",
          Destination: null,
          TopicID: null,
          Attachments: [],
          CreatedAt: new Date().toISOString(),
          UpdatedAt: new Date().toISOString()
        }
      ],
      NextCursor: null
    });

    const chat = useChatStore();
    await chat.fetchMessages();

    expect(chat.messages).toHaveLength(1);
    expect(chat.messages[0]).toMatchObject({
      message_id: "2a2892b3227b427487308d53712dd163",
      state: "propagated",
      scope: "broadcast"
    });
  });

  it("does not downgrade propagated broadcast fallback messages to failed", () => {
    const chat = useChatStore();

    chat.upsertMessage({
      message_id: "2a2892b3227b427487308d53712dd163",
      direction: "outbound",
      scope: "broadcast",
      state: "propagated",
      content: "broadcast",
      attachments: [],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    });
    chat.upsertMessage({
      message_id: "2a2892b3227b427487308d53712dd163",
      direction: "outbound",
      scope: "broadcast",
      state: "failed",
      content: "broadcast",
      attachments: [],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    });

    expect(chat.messages).toHaveLength(1);
    expect(chat.messages[0]).toMatchObject({
      message_id: "2a2892b3227b427487308d53712dd163",
      state: "propagated"
    });
  });
});

import { useConnectionStore } from "./connection";
import { post } from "../api/client";

it("clears pending records and suppression bookkeeping on auth loss without a connection change", () => {
  setActivePinia(createPinia());
  const chat = useChatStore(); const connection = useConnectionStore();
  chat.upsertMessage({ message_id: "pending", created_at: new Date().toISOString(), scope: "broadcast", direction: "outbound", state: "queued" });
  const identity = connection.requestIdentity;
  connection.setAuthStatus("unauthenticated");
  expect(connection.requestIdentity).toBe(identity);
  expect(chat.diagnostics).toMatchObject({ messages: 0, tombstones: 0, reservations: 0, estimatedBytes: 0 });
});

it("refuses a history response from a superseded conversation", async () => {
  setActivePinia(createPinia()); mockedGet.mockReset();
  let complete!: (value: unknown) => void;
  mockedGet.mockImplementationOnce(() => new Promise((resolve) => { complete = resolve; }));
  mockedGet.mockResolvedValueOnce({ Messages: [{ MessageID: "current", Scope: "topic", TopicID: "new" }], NextCursor: null });
  const chat = useChatStore(); const old = chat.fetchMessages();
  await chat.fetchConversation({ scope: "topic", target: "new" });
  complete({ Messages: [{ MessageID: "old", Scope: "broadcast" }], NextCursor: null }); await old;
  expect(chat.messages.map((message) => message.message_id)).toEqual(["current"]);
});

it("does not publish an accepted send to a different backend or after logout", async () => {
  setActivePinia(createPinia()); vi.mocked(post).mockReset();
  let complete!: (value: unknown) => void;
  vi.mocked(post).mockImplementationOnce(() => new Promise((resolve) => { complete = resolve; }));
  const chat = useChatStore();
  const send = chat.sendMessage({ content: "draft", scope: "broadcast", file_ids: [], image_ids: [] });
  expect(chat.diagnostics.reservations).toBe(1);
  useConnectionStore().setAuthStatus("unauthenticated");
  complete({ MessageID: "accepted", Scope: "broadcast", Direction: "outbound", State: "queued" });
  await expect(send).rejects.toThrow("session changed"); expect(chat.messages).toEqual([]);
});


it("keeps incoming and outgoing history in the same direct conversation", async () => {
  setActivePinia(createPinia()); mockedGet.mockReset();
  mockedGet.mockResolvedValue({ Messages: [
    { MessageID: "out", Direction: "outbound", Scope: "dm", Source: null, Destination: "peer", State: "delivered" },
    { MessageID: "in", Direction: "inbound", Scope: "dm", Source: "peer", Destination: "hub", State: "received" }
  ], NextCursor: null });
  const chat = useChatStore(); await chat.fetchConversation({ scope: "dm", target: "peer" });
  expect(chat.visibleMessages.map((message) => message.message_id)).toEqual(["in", "out"]);
});
