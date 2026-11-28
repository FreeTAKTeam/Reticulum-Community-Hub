import { beforeEach, describe, expect, it, vi } from "vitest";
import { decodeChatMessage, fetchChatPage } from "./chat";
vi.mock("./client", () => ({ get: vi.fn(), post: vi.fn() }));
import { get } from "./client";
const mockedGet = vi.mocked(get);
beforeEach(() => { mockedGet.mockReset(); });
describe("chat adapter compatibility", () => {
  it("decodes bounded pages and their opaque cursors", async () => {
    mockedGet.mockResolvedValue({ Messages: [{ MessageID: "b" }, { MessageID: "a" }], NextCursor: "1:2" });
    const result = await fetchChatPage({ scope: "dm", target: "peer" }, 20, null, new AbortController().signal);
    expect(result.messages.map((message) => message.message_id)).toEqual(["a", "b"]);
    expect(mockedGet.mock.calls[0][0]).toContain("peer=peer"); expect(result.nextCursor).toBe("1:2");
  });
  it("retains Python list compatibility and exposes unavailable older paging", async () => {
    mockedGet.mockRejectedValueOnce(Object.assign(new Error("not found"), { status: 404 }));
    mockedGet.mockResolvedValueOnce({ value: [{ MessageID: "legacy", Scope: "broadcast" }], Count: 1 });
    const result = await fetchChatPage({ scope: "broadcast" }, 20, null, new AbortController().signal);
    expect(result.paging).toBe(false); expect(result.messages[0].message_id).toBe("legacy");
    mockedGet.mockRejectedValueOnce(Object.assign(new Error("not found"), { status: 404 }));
    await expect(fetchChatPage({ scope: "broadcast" }, 20, "1:2", new AbortController().signal)).rejects.toThrow("does not support older");
  });
  it("preserves attachment aliases from both shared backends", () => {
    const result = decodeChatMessage({ MessageID: "a", Attachments: [{ file_id: 3, category: "file", name: "old", size: 4, media_type: "text/plain" }] });
    expect(result.attachments?.[0]).toEqual({ file_id: 3, category: "file", name: "old", size: 4, media_type: "text/plain" });
  });
  it("retains only a validated SDK terminal flag", () => {
    expect(decodeChatMessage({ MessageID: "a", DeliveryMetadata: { sdk_terminal: false } }).sdk_terminal).toBe(false);
    expect(() => decodeChatMessage({ MessageID: "a", DeliveryMetadata: { sdk_terminal: "false" } })).toThrow("SDK terminal flag");
    expect(decodeChatMessage({ MessageID: "a" }).sdk_terminal).toBeUndefined();
  });
  it("does not conceal malformed responses or auth/server errors", async () => {
    expect(() => decodeChatMessage({ Content: "missing ID" })).toThrow("MessageID");
    mockedGet.mockResolvedValue([]);
    await expect(fetchChatPage({ scope: "broadcast" }, 20, null, new AbortController().signal)).rejects.toThrow();
    mockedGet.mockRejectedValue(Object.assign(new Error("forbidden"), { status: 403 }));
    await expect(fetchChatPage({ scope: "broadcast" }, 20, null, new AbortController().signal)).rejects.toThrow("forbidden");
  });
});
