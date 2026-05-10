import { defineStore } from "pinia";
import { ref } from "vue";
import { endpoints } from "../api/endpoints";
import { get } from "../api/client";
import { post } from "../api/client";
import type { ChatAttachment } from "../api/types";
import type { ChatMessage } from "../api/types";

type ChatAttachmentPayload = {
  FileID?: number;
  Category?: string;
  Name?: string;
  Size?: number;
  MediaType?: string | null;
};

type ChatMessagePayload = {
  MessageID?: string;
  Direction?: string;
  Scope?: string;
  State?: string;
  Content?: string;
  Source?: string | null;
  Destination?: string | null;
  TopicID?: string | null;
  Attachments?: ChatAttachmentPayload[];
  CreatedAt?: string;
  UpdatedAt?: string;
};

const fromApiAttachment = (payload: ChatAttachmentPayload): ChatAttachment => ({
  file_id: payload.FileID,
  category: payload.Category,
  name: payload.Name,
  size: payload.Size,
  media_type: payload.MediaType ?? undefined
});

const fromApiMessage = (payload: ChatMessagePayload): ChatMessage => ({
  message_id: payload.MessageID,
  direction: payload.Direction,
  scope: payload.Scope,
  state: payload.State,
  content: payload.Content,
  source: payload.Source ?? undefined,
  destination: payload.Destination ?? undefined,
  topic_id: payload.TopicID ?? undefined,
  attachments: payload.Attachments?.map(fromApiAttachment) ?? [],
  created_at: payload.CreatedAt,
  updated_at: payload.UpdatedAt
});

export const useChatStore = defineStore("chat", () => {
  const messages = ref<ChatMessage[]>([]);
  const loading = ref(false);

  const fetchMessages = async (limit = 200) => {
    loading.value = true;
    try {
      const response = await get<ChatMessagePayload[]>(`${endpoints.chatMessages}?limit=${limit}`);
      messages.value = response.map(fromApiMessage).reverse();
    } finally {
      loading.value = false;
    }
  };

  const sendMessage = async (payload: {
    content?: string;
    scope: string;
    topic_id?: string;
    destination?: string;
    file_ids: number[];
    image_ids: number[];
  }) => {
    const response = await post<ChatMessagePayload>(endpoints.chatMessage, {
      Content: payload.content,
      Scope: payload.scope,
      TopicID: payload.topic_id,
      Destination: payload.destination,
      FileIDs: payload.file_ids,
      ImageIDs: payload.image_ids
    });
    const message = fromApiMessage(response);
    upsertMessage(message);
    return message;
  };

  const uploadAttachment = async (payload: {
    category: "file" | "image";
    file: File;
    sha256?: string;
    topic_id?: string;
  }) => {
    const form = new FormData();
    form.append("category", payload.category);
    form.append("file", payload.file, payload.file.name);
    if (payload.sha256) {
      form.append("sha256", payload.sha256);
    }
    if (payload.topic_id) {
      form.append("topic_id", payload.topic_id);
    }
    const response = await post<ChatAttachmentPayload>(endpoints.chatAttachment, form);
    return fromApiAttachment(response);
  };

  const upsertMessage = (message: ChatMessage) => {
    if (!message.message_id) {
      messages.value.push(message);
      return;
    }
    const index = messages.value.findIndex((entry) => entry.message_id === message.message_id);
    if (index >= 0) {
      messages.value[index] = { ...messages.value[index], ...message };
    } else {
      messages.value.push(message);
    }
  };

  return {
    messages,
    loading,
    fetchMessages,
    sendMessage,
    uploadAttachment,
    upsertMessage
  };
});
