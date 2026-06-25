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
      value: [
        {
          MessageID: "2a2892b3227b427487308d53712dd163",
          Direction: "outbound",
          Scope: "broadcast",
          State: "propagated",
          Content: "broadcast",
          Destination: null,
          TopicID: null,
          Attachments: [],
          CreatedAt: "2026-06-23T02:00:00.000Z",
          UpdatedAt: "2026-06-23T02:01:00.000Z"
        }
      ],
      Count: 1
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
      created_at: "2026-06-23T02:00:00.000Z",
      updated_at: "2026-06-23T02:01:00.000Z"
    });
    chat.upsertMessage({
      message_id: "2a2892b3227b427487308d53712dd163",
      direction: "outbound",
      scope: "broadcast",
      state: "failed",
      content: "broadcast",
      attachments: [],
      created_at: "2026-06-23T02:00:00.000Z",
      updated_at: "2026-06-23T02:02:00.000Z"
    });

    expect(chat.messages).toHaveLength(1);
    expect(chat.messages[0]).toMatchObject({
      message_id: "2a2892b3227b427487308d53712dd163",
      state: "propagated"
    });
  });
});
