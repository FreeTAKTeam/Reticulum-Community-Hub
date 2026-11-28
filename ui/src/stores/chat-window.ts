import type { ChatMessage } from "../api/types";
import { conversationKey, conversationOf, type Conversation } from "../api/chat";
import type { ChatRetentionConfig } from "../config/chat-retention";

type Entry = { message: ChatMessage; touched: number; sequence: number; order: number; bytes: number };
type Tombstone = { state?: string; sdk_terminal?: boolean; touched: number; bytes: number };
const successful = new Set(["delivered", "propagated", "sent"]);
const terminal = new Set(["received", "failed", ...successful]);
const state = (message: ChatMessage) => String(message.state ?? "").trim().toLowerCase();
// Rust SDK sent can still await a receipt; legacy backends omit this flag.
const success = (message: ChatMessage) => successful.has(state(message)) && !(state(message) === "sent" && message.sdk_terminal === false);
const completed = (message: ChatMessage) => terminal.has(state(message)) && !(state(message) === "sent" && message.sdk_terminal === false);
const pending = (message: ChatMessage) => message.direction === "outbound" && !completed(message);
const keyOf = (message: ChatMessage) => message.message_id?.trim().toLowerCase() ?? "";
export const estimateMessageBytes = (message: ChatMessage) => 1024 + Object.values(message).reduce<number>((size, value) =>
  size + (typeof value === "string" ? value.length * 2 : 0), 0) + (message.attachments ?? []).reduce((size, attachment) =>
  size + 256 + Object.values(attachment).reduce<number>((sum, value) => sum + (typeof value === "string" ? value.length * 2 : 0), 0), 0);
const merge = (current: ChatMessage, incoming: ChatMessage): ChatMessage => {
  const patch = Object.fromEntries(Object.entries(incoming).filter(([, value]) => value !== undefined));
  const combined = { ...current, ...patch };
  // A presentation guard for delayed events; the backend remains the lifecycle owner.
  if (success(current) && !success(combined)) { combined.state = current.state; combined.sdk_terminal = current.sdk_terminal; }
  return combined;
};

/** One bounded presentation owner. Maps share entries; derived arrays are views. */
export class ChatWindow {
  private entries = new Map<string, Entry>();
  private buckets = new Map<string, Set<string>>();
  private tombstones = new Map<string, Tombstone>();
  private reservations = new Map<symbol, { key: string; bytes: number }>();
  private serial = 0;
  private order = 0;
  rejected = 0;
  evictions = 0;
  omittedUpdates = 0;
  capacityBlocked = false;
  constructor(readonly config: ChatRetentionConfig, private now = () => Date.now()) {}
  get sequence() { return this.serial; }
  get size() { return this.entries.size; }
  get bytes() { return [...this.entries.values()].reduce((n, entry) => n + entry.bytes, 0) + [...this.tombstones.values()].reduce((n, entry) => n + entry.bytes, 0) + [...this.reservations.values()].reduce((n, entry) => n + entry.bytes, 0); }
  values(conversation?: Conversation): ChatMessage[] {
    const ids = conversation ? this.buckets.get(conversationKey(conversation)) ?? [] : this.entries.keys();
    return [...ids].flatMap((id) => { const entry = this.entries.get(id); return entry ? [entry] : []; })
      .sort((a, b) => (Date.parse(a.message.created_at ?? "") || 0) - (Date.parse(b.message.created_at ?? "") || 0) || a.order - b.order)
      .map((entry) => entry.message);
  }
  clear() {
    this.entries.clear(); this.buckets.clear(); this.tombstones.clear(); this.reservations.clear();
    this.serial++; this.capacityBlocked = false; this.rejected = 0; this.evictions = 0; this.omittedUpdates = 0;
  }
  private remove(id: string) {
    const entry = this.entries.get(id);
    if (!entry) { return; }
    const key = conversationKey(conversationOf(entry.message));
    this.entries.delete(id);
    const bucket = this.buckets.get(key); bucket?.delete(id);
    if (!bucket?.size) { this.buckets.delete(key); }
    this.remember(id, entry.message);
    this.evictions++;
  }
  private remember(id: string, message: ChatMessage) {
    const previous = this.tombstones.get(id);
    const preserved = merge(previous ?? {}, message);
    this.tombstones.delete(id);
    this.tombstones.set(id, { state: preserved.state, sdk_terminal: preserved.sdk_terminal, touched: this.now(), bytes: 256 + id.length * 2 });
    while (this.tombstones.size > this.config.tombstones || this.bytes > this.config.globalBytes) {
      const oldest = this.tombstones.keys().next().value;
      if (oldest === undefined) { break; }
      this.tombstones.delete(oldest);
    }
  }
  maintain() {
    const cutoff = this.now() - this.config.idleMs;
    for (const [id, entry] of this.entries) { if (!pending(entry.message) && entry.touched <= cutoff) { this.remove(id); } }
    for (const [id, entry] of this.tombstones) { if (entry.touched <= cutoff) { this.tombstones.delete(id); } }
    this.capacityBlocked = !this.fits("", 1, 1024);
  }
  private fits(key: string, count: number, bytes: number) {
    const reserved = [...this.reservations.values()];
    return this.size + reserved.length + count <= this.config.globalMessages && this.bytes + bytes <= this.config.globalBytes &&
      (!key || (this.buckets.get(key)?.size ?? 0) + reserved.filter((entry) => entry.key === key).length + count <= this.config.conversationMessages);
  }
  private makeRoom(key: string, count: number, bytes: number, excluding = "") {
    while (!this.fits(key, count, bytes)) {
      const overConversation = (this.buckets.get(key)?.size ?? 0) + [...this.reservations.values()].filter((entry) => entry.key === key).length + count > this.config.conversationMessages;
      const candidates = [...this.entries].filter(([id, entry]) => id !== excluding && !pending(entry.message) && (!overConversation || conversationKey(conversationOf(entry.message)) === key));
      candidates.sort((a, b) => a[1].touched - b[1].touched || a[1].order - b[1].order);
      if (!candidates.length) {
        // Suppression metadata can be shed before rejecting protected work.
        this.tombstones.clear();
        return this.fits(key, count, bytes);
      }
      this.remove(candidates[0][0]);
    }
    return true;
  }
  reserve(conversation: Conversation, bytes: number): symbol {
    this.maintain();
    const key = conversationKey(conversation);
    if (!this.makeRoom(key, 1, bytes)) {
      this.capacityBlocked = true;
      throw new Error("Chat window is full of pending messages. Wait for delivery before sending again.");
    }
    const token = Symbol("chat send"); this.reservations.set(token, { key, bytes }); return token;
  }
  release(token: symbol) { this.reservations.delete(token); this.capacityBlocked = false; }
  upsert(message: ChatMessage, source: "live" | "history" | "send" = "live"): boolean {
    this.maintain();
    const id = keyOf(message);
    if (!id || id.length > 256) { this.rejected++; return false; }
    const previous = this.entries.get(id);
    const tombstone = this.tombstones.get(id);
    const created = Date.parse(message.created_at ?? "");
    if (!previous && source === "live" && !Number.isFinite(created)) { this.rejected++; return false; }
    // Unrequested old receipts must not resurrect history after suppression IDs expire.
    if (!previous && source === "live" && ((Number.isFinite(created) && created < this.now() - this.config.idleMs) || tombstone)) {
      this.remember(id, merge(tombstone ?? {}, message)); return false;
    }
    let combined = merge(previous?.message ?? { state: tombstone?.state, sdk_terminal: tombstone?.sdk_terminal }, message);
    let key = conversationKey(conversationOf(combined));
    let bytes = estimateMessageBytes(combined);
    const delta = bytes - (previous?.bytes ?? 0);
    const oldKey = previous ? conversationKey(conversationOf(previous.message)) : undefined;
    if (!this.makeRoom(key, previous && oldKey === key ? 0 : 1, delta, id)) {
      this.rejected++;
      // A receipt can complete protected work even when accompanying details are too large.
      // Keep the retained payload and apply only a bounded, known terminal lifecycle state.
      if (previous && completed(combined)) {
        this.omittedUpdates++;
        combined = { ...previous.message, state: state(combined), sdk_terminal: combined.sdk_terminal };
        key = oldKey!;
        bytes = estimateMessageBytes(combined);
        if (!this.makeRoom(oldKey!, 0, bytes - previous.bytes, id)) {
          this.remove(id); this.remember(id, combined); this.serial++;
          this.capacityBlocked = false; return true;
        }
      } else { this.capacityBlocked = true; return false; }
    }
    if (previous && oldKey !== key) { this.remove(id); }
    this.tombstones.delete(id);
    this.entries.set(id, { message: combined, bytes, touched: this.now(), sequence: ++this.serial, order: previous?.order ?? ++this.order });
    const bucket = this.buckets.get(key) ?? new Set<string>(); bucket.add(id); this.buckets.set(key, bucket);
    this.capacityBlocked = false; return true;
  }
  replacePage(conversation: Conversation, messages: ChatMessage[], started: number) {
    const key = conversationKey(conversation);
    let omissions = 0;
    for (const id of [...(this.buckets.get(key) ?? [])]) {
      const entry = this.entries.get(id);
      if (entry && !pending(entry.message) && entry.sequence <= started) { this.remove(id); }
    }
    for (const [index, message] of messages.entries()) {
      const entry = this.entries.get(keyOf(message));
      if (entry && entry.sequence > started) { continue; }
      const hadEntry = !!entry;
      const omittedBefore = this.omittedUpdates;
      if (!this.upsert(message, "history") || this.omittedUpdates > omittedBefore) { omissions++; }
      const inserted = this.entries.get(keyOf(message));
      if (inserted && !hadEntry) { inserted.order = index - messages.length; }
    }
    return omissions;
  }
  diagnostics() {
    return { messages: this.size, estimatedBytes: this.bytes, conversations: this.buckets.size, tombstones: this.tombstones.size,
      pending: [...this.entries.values()].filter((entry) => pending(entry.message)).length, reservations: this.reservations.size,
      evictions: this.evictions, rejected: this.rejected, omittedUpdates: this.omittedUpdates, capacityBlocked: this.capacityBlocked, limits: this.config };
  }
}
