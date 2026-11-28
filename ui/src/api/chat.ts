import { get, post, type ApiError } from "./client";
import { endpoints } from "./endpoints";
import type { ChatAttachment, ChatMessage } from "./types";
import { unwrapApiList } from "../utils/api-list";

export type Conversation = { scope: "dm" | "topic" | "broadcast"; target?: string };
export type ChatPage = { messages: ChatMessage[]; nextCursor: string | null; paging: boolean };
const object = (value: unknown): Record<string, unknown> => {
  if (!value || typeof value !== "object" || Array.isArray(value)) { throw new Error("Invalid chat response object."); }
  return value as Record<string, unknown>;
};
const text = (value: unknown): string | undefined => typeof value === "string" ? value : undefined;
export const decodeAttachment = (value: unknown): ChatAttachment => {
  const item = object(value);
  return {
    file_id: typeof (item.FileID ?? item.file_id) === "number" ? (item.FileID ?? item.file_id) as number : undefined,
    category: text(item.Category ?? item.category), name: text(item.Name ?? item.name),
    size: typeof (item.Size ?? item.size) === "number" ? (item.Size ?? item.size) as number : undefined, media_type: text(item.MediaType ?? item.media_type)
  };
};
export const decodeChatMessage = (value: unknown): ChatMessage => {
  const item = object(value);
  const id = text(item.MessageID);
  if (!id?.trim()) { throw new Error("Chat message has no MessageID."); }
  const metadata = item.DeliveryMetadata;
  const terminal = metadata && typeof metadata === "object" && !Array.isArray(metadata)
    ? (metadata as Record<string, unknown>).sdk_terminal : undefined;
  if (terminal !== undefined && typeof terminal !== "boolean") { throw new Error("Invalid chat SDK terminal flag."); }
  return {
    sdk_terminal: typeof terminal === "boolean" ? terminal : undefined,
    message_id: id, direction: text(item.Direction), scope: text(item.Scope), state: text(item.State),
    content: text(item.Content), source: text(item.Source), destination: text(item.Destination),
    topic_id: text(item.TopicID), created_at: text(item.CreatedAt), updated_at: text(item.UpdatedAt),
    attachments: Array.isArray(item.Attachments) ? item.Attachments.map(decodeAttachment) : undefined
  };
};
export const conversationOf = (message: ChatMessage): Conversation => {
  const scope = message.scope?.trim().toLowerCase();
  if (scope === "topic" || (!scope && message.topic_id)) { return { scope: "topic", target: message.topic_id ?? undefined }; }
  if (scope === "dm" || (!scope && message.destination)) {
    return { scope: "dm", target: (message.direction === "inbound" ? message.source : message.destination) ?? undefined };
  }
  return { scope: "broadcast" };
};
export const conversationKey = (conversation: Conversation) => JSON.stringify([conversation.scope, conversation.target ?? ""]);
export const fetchChatPage = async (conversation: Conversation, limit: number, cursor: string | null, signal: AbortSignal): Promise<ChatPage> => {
  const query = new URLSearchParams({ scope: conversation.scope, limit: String(limit) });
  if (conversation.target) { query.set(conversation.scope === "dm" ? "peer" : "topic_id", conversation.target); }
  if (cursor) { query.set("cursor", cursor); }
  try {
    const payload = object(await get<unknown>(`/Chat/History?${query}`, { signal }));
    if (!Array.isArray(payload.Messages) || !(payload.NextCursor === null || typeof payload.NextCursor === "string")) {
      throw new Error("Invalid paged chat history response.");
    }
    return { messages: payload.Messages.map(decodeChatMessage).reverse(), nextCursor: payload.NextCursor, paging: true };
  } catch (error) {
    if (![404, 405].includes((error as ApiError).status ?? 0)) { throw error; }
    if (cursor) { throw new Error("This backend does not support older chat history pages."); }
    const legacy = new URLSearchParams({ limit: String(limit) });
    if (conversation.scope === "topic" && conversation.target) { legacy.set("topic_id", conversation.target); }
    const response = await get<unknown>(`${endpoints.chatMessages}?${legacy}`, { signal });
    return { messages: unwrapApiList<unknown>(response).map(decodeChatMessage).reverse().filter((message) => conversationKey(conversationOf(message)) === conversationKey(conversation)), nextCursor: null, paging: false };
  }
};
export type SendChat = { content?: string; scope: string; topic_id?: string; destination?: string; file_ids: number[]; image_ids: number[] };
export const postChat = async (payload: SendChat, signal: AbortSignal) => decodeChatMessage(await post<unknown>(endpoints.chatMessage, {
  Content: payload.content, Scope: payload.scope, TopicID: payload.topic_id, Destination: payload.destination,
  FileIDs: payload.file_ids, ImageIDs: payload.image_ids
}, { signal, retries: 0 }));
