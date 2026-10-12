import { computed, onScopeDispose, ref, watch } from "vue";
import { defineStore } from "pinia";
import { post } from "../api/client";
import { endpoints } from "../api/endpoints";
import { decodeAttachment, fetchChatPage, postChat, type Conversation, type SendChat } from "../api/chat";
import type { ChatMessage } from "../api/types";
import { resolveChatRetention } from "../config/chat-retention";
import { useConnectionStore } from "./connection";
import { ChatWindow } from "./chat-window";

export const useChatStore = defineStore("chat", () => {
  const connection = useConnectionStore();
  const cache = new ChatWindow(resolveChatRetention());
  const revision = ref(0);
  const loading = ref(false);
  const error = ref("");
  const conversation = ref<Conversation>({ scope: "broadcast" });
  const nextCursor = ref<string | null>(null);
  const paging = ref(true);
  const viewingHistory = ref(false);
  let epoch = 0;
  let pageRequest = 0;
  let controller: AbortController | undefined;
  let maintenance: ReturnType<typeof setInterval> | undefined;
  const requests = new Set<AbortController>();
  const publish = () => { revision.value++; };
  const messages = computed(() => { void revision.value; return cache.values(); });
  const visibleMessages = computed(() => { void revision.value; return cache.values(conversation.value); });
  const diagnostics = computed(() => { void revision.value; return cache.diagnostics(); });
  const stop = () => {
    if (maintenance) { clearInterval(maintenance); maintenance = undefined; }
    controller?.abort(); controller = undefined;
    pageRequest++; loading.value = false;
  };
  const reset = () => {
    epoch++; stop(); requests.forEach((request) => request.abort()); requests.clear(); cache.clear();
    nextCursor.value = null; viewingHistory.value = false; error.value = ""; paging.value = true; publish();
  };
  watch(() => connection.requestIdentity, reset, { flush: "sync" });
  watch(() => connection.authStatus, (status) => { if (status === "unauthenticated") { reset(); } }, { flush: "sync" });
  watch(() => connection.isAuthenticated, (current, previous) => { if (previous && !current) { reset(); } }, { flush: "sync" });
  const start = () => {
    if (maintenance) { return; }
    cache.maintain(); publish();
    maintenance = setInterval(() => { cache.maintain(); publish(); }, cache.config.maintenanceMs);
  };
  onScopeDispose(reset);
  const assertEpoch = (captured: number) => {
    if (epoch !== captured) { throw new DOMException("Chat backend session changed", "AbortError"); }
  };
  const fetchConversation = async (selected = conversation.value, older = false, limit = cache.config.pageSize) => {
    controller?.abort();
    const current = new AbortController(); controller = current;
    const captured = epoch; const request = ++pageRequest; const sequence = cache.sequence;
    const cursor = older ? nextCursor.value : null;
    if (older && !cursor) { return; }
    conversation.value = { ...selected }; loading.value = true; error.value = "";
    try {
      const result = await fetchChatPage(selected, Math.min(limit, cache.config.conversationMessages), cursor, current.signal);
      assertEpoch(captured);
      if (request !== pageRequest) { return; }
      const omissions = cache.replacePage(selected, result.messages, sequence); publish();
      nextCursor.value = result.nextCursor; paging.value = result.paging; viewingHistory.value = older;
      if (omissions) { error.value = "Some history records exceed the configured chat window. Full details remain on the server."; }
      else if (cache.capacityBlocked) { error.value = "Chat window is full of pending messages. Some history remains on the server."; }
    } catch (failure) {
      if (captured === epoch && request === pageRequest && !current.signal.aborted) {
        error.value = failure instanceof Error ? failure.message : "Unable to load chat history.";
      }
      throw failure;
    } finally {
      if (captured === epoch && request === pageRequest) { loading.value = false; controller = undefined; }
    }
  };
  const fetchMessages = (limit = cache.config.pageSize) => fetchConversation(conversation.value, false, limit);
  const loadOlder = () => fetchConversation(conversation.value, true);
  const upsertMessage = (message: ChatMessage) => {
    const omitted = cache.omittedUpdates;
    const admitted = cache.upsert(message); publish();
    if (cache.omittedUpdates > omitted) { error.value = "Message details exceed the chat memory budget. Delivery state was retained; full details remain in server history."; }
    if (cache.capacityBlocked) { error.value = "Chat window is full of pending messages. Wait for delivery or open server history."; }
    return admitted;
  };
  const sendMessage = async (payload: SendChat) => {
    const selected: Conversation = { scope: payload.scope === "dm" ? "dm" : payload.scope === "topic" ? "topic" : "broadcast", target: payload.destination ?? payload.topic_id };
    const reservedBytes = 2048 + (payload.content?.length ?? 0) * 2 + (payload.file_ids.length + payload.image_ids.length) * 4096;
    const reservation = cache.reserve(selected, reservedBytes); publish();
    const captured = epoch; const current = new AbortController(); requests.add(current);
    try {
      const message = await postChat(payload, current.signal); assertEpoch(captured);
      cache.release(reservation);
      if (!cache.upsert(message, "send")) { throw new Error("Message was accepted by the server but exceeds the chat window budget. Refresh history to inspect it."); }
      publish(); return message;
    } finally { requests.delete(current); if (captured === epoch) { cache.release(reservation); publish(); } }
  };
  const uploadAttachment = async (payload: { category: "file" | "image"; file: File; sha256?: string; topic_id?: string }) => {
    const captured = epoch; const current = new AbortController(); requests.add(current);
    const form = new FormData(); form.append("category", payload.category); form.append("file", payload.file, payload.file.name);
    if (payload.sha256) { form.append("sha256", payload.sha256); }
    if (payload.topic_id) { form.append("topic_id", payload.topic_id); }
    try {
      const response = await post<unknown>(endpoints.chatAttachment, form, { signal: current.signal, retries: 0 });
      assertEpoch(captured); return decodeAttachment(response);
    } finally { requests.delete(current); }
  };
  return { messages, visibleMessages, diagnostics, loading, error, conversation, nextCursor, paging, viewingHistory,
    fetchMessages, fetchConversation, loadOlder, sendMessage, uploadAttachment, upsertMessage, start, stop, reset };
});
