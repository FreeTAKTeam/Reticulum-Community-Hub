import { describe, expect, it } from "vitest";
import { ChatWindow, estimateMessageBytes } from "./chat-window";
import defaults from "../config/chat-retention.json";
import { resolveChatRetention } from "../config/chat-retention";
const message = (id: string, overrides = {}) => ({ message_id: id, scope: "broadcast", direction: "inbound", state: "received", content: "sample", created_at: new Date().toISOString(), ...overrides });

describe("configured chat window", () => {
  it("reads policy overrides and rejects invalid bounds", () => {
    expect(resolveChatRetention({ VITE_CHAT_GLOBAL_BYTES: "99999" }).globalBytes).toBe(99999);
    expect(() => resolveChatRetention({ VITE_CHAT_PAGE_SIZE: "201" })).toThrow();
    expect(() => resolveChatRetention({ VITE_CHAT_IDLE_MS: "0" })).toThrow();
  });
  it("bounds sustained traffic, conversations, bytes and suppression IDs", () => {
    const cache = new ChatWindow({ ...defaults, conversationMessages: 10, globalMessages: 20, globalBytes: 40000, tombstones: 25, pageSize: 10 });
    for (let i = 0; i < 2000; i++) {
      cache.upsert(message(String(i), { scope: "topic", topic_id: `topic-${i % 3}` }));
      expect(cache.size).toBeLessThanOrEqual(20); expect(cache.bytes).toBeLessThanOrEqual(40000);
    }
    expect(cache.diagnostics().tombstones).toBeLessThanOrEqual(25);
    for (let i = 0; i < 3; i++) { expect(cache.values({ scope: "topic", target: `topic-${i}` }).length).toBeLessThanOrEqual(10); }
  });
  it("protects pending work and rejects excess admissions and sends", () => {
    const cache = new ChatWindow({ ...defaults, conversationMessages: 2, globalMessages: 2, pageSize: 2 });
    cache.upsert(message("pending-1", { direction: "outbound", state: "queued" }));
    cache.upsert(message("pending-2", { direction: "outbound", state: "retrying" }));
    expect(cache.upsert(message("new"))).toBe(false);
    expect(() => cache.reserve({ scope: "broadcast" }, 2048)).toThrow("pending messages");
    cache.upsert(message("pending-1", { direction: "outbound", state: "delivered" }));
    const token = cache.reserve({ scope: "broadcast" }, 2048);
    expect(cache.values().find((entry) => entry.message_id === "pending-2")?.state).toBe("retrying");
    cache.release(token);
  });
  it("protects SDK sent awaiting receipt and allows its eventual failure", () => {
    let now = Date.now();
    const cache = new ChatWindow({ ...defaults, conversationMessages: 1, pageSize: 1 }, () => now);
    cache.upsert(message("sdk", { direction: "outbound", state: "sent", sdk_terminal: false }));
    now += defaults.idleMs; cache.maintain();
    expect(cache.diagnostics().pending).toBe(1);
    expect(cache.upsert(message("new"))).toBe(false);
    cache.upsert(message("sdk", { direction: "outbound", state: "failed", sdk_terminal: true }));
    expect(cache.values()[0].state).toBe("failed"); expect(cache.diagnostics().pending).toBe(0);
  });
  it("preserves completed SDK and legacy sent through tombstones", () => {
    for (const flag of [true, undefined]) {
      const cache = new ChatWindow({ ...defaults, conversationMessages: 1, pageSize: 1 });
      cache.upsert(message("sent", { direction: "outbound", state: "sent", sdk_terminal: flag }));
      cache.upsert(message("new"));
      cache.replacePage({ scope: "broadcast" }, [message("sent", { direction: "outbound", state: "sent", sdk_terminal: false })], cache.sequence);
      expect(cache.values()[0].sdk_terminal).toBe(flag);
      expect(cache.diagnostics().pending).toBe(0);
    }
  });
  it("protects successful delivery through eviction, paging and late failure", () => {
    let now = 10000;
    const cache = new ChatWindow({ ...defaults, conversationMessages: 1, globalMessages: 2, pageSize: 1 }, () => now);
    cache.upsert(message("A", { direction: "outbound", state: "delivered" }));
    cache.upsert(message("B"));
    cache.upsert(message("a", { direction: "outbound", state: "failed" }));
    expect(cache.size).toBe(1);
    cache.replacePage({ scope: "broadcast" }, [message("A", { direction: "outbound", state: "queued" })], cache.sequence);
    expect(cache.values()[0].state).toBe("delivered");
    now += defaults.idleMs;
    cache.maintain(); expect(cache.size).toBe(0);
    cache.upsert(message("A", { created_at: new Date(10000).toISOString() }));
    expect(cache.size).toBe(0);
  });
  it("uses activity expiry but retains pending and prevents history overwriting live", () => {
    let now = 100;
    const cache = new ChatWindow(defaults, () => now);
    cache.upsert(message("old")); cache.upsert(message("pending", { direction: "outbound", state: "queued" }));
    const sequence = cache.sequence;
    cache.upsert(message("old", { state: "delivered", content: "live update" }));
    cache.replacePage({ scope: "broadcast" }, [message("old", { state: "failed" })], sequence);
    expect(cache.values().find((entry) => entry.message_id === "old")?.content).toBe("live update");
    now += defaults.idleMs; cache.maintain(); expect(cache.values().map((entry) => entry.message_id)).toEqual(["pending"]);
    cache.clear(); expect(cache.diagnostics()).toMatchObject({ messages: 0, estimatedBytes: 0, conversations: 0, tombstones: 0, reservations: 0 });
  });
  it("reports mixed history omissions even when later entries fit", () => {
    const cache = new ChatWindow({ ...defaults, globalBytes: 4096 });
    const omissions = cache.replacePage({ scope: "broadcast" }, [message("huge", { content: "x".repeat(10000) }), message("fits")], cache.sequence);
    expect(omissions).toBe(1); expect(cache.values()[0].message_id).toBe("fits");
  });
  it("includes content and attachment metadata in byte admission", () => {
    const cache = new ChatWindow({ ...defaults, globalBytes: 4096 });
    const large = message("huge", { content: "x".repeat(10000) });
    expect(estimateMessageBytes(large)).toBeGreaterThan(4096); expect(cache.upsert(large)).toBe(false); expect(cache.bytes).toBeLessThanOrEqual(4096);
  });
  it("accepts terminal receipts without retaining oversized accompanying details", () => {
    const original = message("pending", { direction: "outbound", state: "queued" });
    const cache = new ChatWindow({ ...defaults, globalBytes: estimateMessageBytes(original) + 64 });
    cache.upsert(original);
    cache.upsert(message("pending", { direction: "outbound", state: "delivered", content: "x".repeat(10000), attachments: [{ name: "y".repeat(10000) }] }));
    expect(cache.values()[0]).toMatchObject({ state: "delivered", content: "sample" });
    expect(cache.diagnostics()).toMatchObject({ pending: 0, omittedUpdates: 1 });
    cache.upsert(message("pending", { direction: "outbound", state: "failed", content: "x".repeat(10000) }));
    expect(cache.values()[0].state).toBe("delivered");
    expect(cache.bytes).toBeLessThanOrEqual(cache.config.globalBytes);
    const token = cache.reserve({ scope: "broadcast" }, 1024); cache.release(token);
  });
  it("carries SDK completion through an oversized receipt and eviction", () => {
    const original = message("sdk", { direction: "outbound", state: "sent", sdk_terminal: false });
    const cache = new ChatWindow({ ...defaults, globalBytes: estimateMessageBytes(original) + 1024 });
    cache.upsert(original);
    expect(cache.upsert(message("sdk", { direction: "outbound", state: "sent", sdk_terminal: true, content: "x".repeat(10000) }))).toBe(true);
    expect(cache.diagnostics()).toMatchObject({ pending: 0, omittedUpdates: 1 });
    cache.upsert(message("other"));
    cache.replacePage({ scope: "broadcast" }, [original], cache.sequence);
    expect(cache.values()[0]).toMatchObject({ state: "sent", sdk_terminal: true });
    expect(cache.diagnostics().pending).toBe(0);
  });
  it("evicts a completed view at exact byte saturation instead of protecting stale pending state", () => {
    const original = message("pending", { direction: "outbound", state: "queued" });
    const cache = new ChatWindow({ ...defaults, globalBytes: estimateMessageBytes(original) });
    cache.upsert(original);
    cache.upsert(message("pending", { direction: "outbound", state: "delivered", content: "x".repeat(10000) }));
    expect(cache.diagnostics().pending).toBe(0); expect(cache.bytes).toBeLessThanOrEqual(cache.config.globalBytes);
  });
  it("accounts for concurrent send reservations and rejects unbounded states", () => {
    const cache = new ChatWindow({ ...defaults, conversationMessages: 2, globalMessages: 2, pageSize: 2 });
    const first = cache.reserve({ scope: "broadcast" }, 4096);
    const second = cache.reserve({ scope: "broadcast" }, 4096);
    expect(cache.diagnostics()).toMatchObject({ reservations: 2, estimatedBytes: 8192 });
    expect(() => cache.reserve({ scope: "broadcast" }, 4096)).toThrow();
    cache.release(first); cache.release(second);
    cache.upsert(message("pending", { direction: "outbound", state: "queued" }));
    expect(cache.upsert(message("pending", { direction: "outbound", state: "x".repeat(defaults.globalBytes) }))).toBe(false);
    expect(cache.diagnostics().pending).toBe(1);
  });

});
