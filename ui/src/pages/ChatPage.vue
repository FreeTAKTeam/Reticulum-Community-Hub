<template>
  <div class="chat-cosmos">
    <div class="chat-shell">
      <header class="chat-top">
        <div>
          <div class="chat-title">Communications Grid</div>
          <div class="chat-subtitle">Direct, topic, and broadcast channels with live attachment flow</div>
        </div>
        <div class="chat-badges">
          <div class="chat-badge">
            <span>Scope</span>
            <strong>{{ activeScope.toUpperCase() }}</strong>
          </div>
          <div class="chat-badge">
            <span>Messages</span>
            <strong>{{ visibleMessages.length }}</strong>
          </div>
          <div class="chat-badge">
            <span>Queued Files</span>
            <strong>{{ pendingAttachments.length }}</strong>
          </div>
        </div>
      </header>

      <div class="chat-grid">
        <aside class="panel chat-directory">
          <div class="panel-header">
            <div>
              <div class="panel-title">Directory</div>
              <div class="panel-subtitle">Select a communications lane</div>
            </div>
            <div class="panel-chip">{{ directoryTab === "peers" ? filteredPeers.length : filteredTopics.length }}</div>
          </div>

          <div class="directory-search">
            <label for="chat-directory-search">Filter</label>
            <input id="chat-directory-search" v-model="searchQuery" type="text" placeholder="Filter users or topics" />
          </div>

          <div class="panel-tabs">
            <button class="panel-tab" :class="{ active: directoryTab === 'peers' }" type="button" @click="directoryTab = 'peers'">
              Users
            </button>
            <button class="panel-tab" :class="{ active: directoryTab === 'topics' }" type="button" @click="directoryTab = 'topics'">
              Topics
            </button>
          </div>

          <div class="directory-list chat-directory-scroll">
            <template v-if="directoryTab === 'peers'">
              <button
                v-for="peer in filteredPeers"
                :key="peer.id"
                class="directory-item"
                :class="{ active: peer.id === activePeer && activeScope === 'dm' }"
                @click="selectConversation('dm', peer.id)"
              >
                <span class="directory-primary">
                  <span class="presence-dot" :class="{ online: peer.online }" aria-hidden="true"></span>
                  <span class="truncate">{{ peer.label }}</span>
                </span>
                <span class="directory-tag">DM</span>
              </button>
            </template>
            <template v-else>
              <button
                v-for="topic in filteredTopics"
                :key="topic.id"
                class="directory-item"
                :class="{ active: topic.id === activeTopic && activeScope === 'topic' }"
                @click="selectConversation('topic', topic.id)"
              >
                <span class="directory-primary">
                  <span class="truncate">{{ topic.label }}</span>
                </span>
                <span class="directory-tag">Topic</span>
              </button>
            </template>
            <button
              class="directory-item directory-item--broadcast"
              :class="{ active: activeScope === 'broadcast' }"
              @click="selectConversation('broadcast')"
            >
              <span class="directory-primary">
                <span class="truncate">Broadcast</span>
              </span>
              <span class="directory-tag">All</span>
            </button>
          </div>
        </aside>

        <section class="panel chat-main">
          <div class="conversation-head">
            <div>
              <div class="panel-title">Conversation: {{ activeLabel }}</div>
              <div class="panel-subtitle">Delivery state inline</div>
            </div>
            <div class="conversation-state">
              <span class="scope-pill">{{ activeScope.toUpperCase() }}</span>
              <BaseButton variant="secondary" icon-left="refresh" @click="chatStore.fetchMessages()">Refresh</BaseButton>
            </div>
          </div>

          <div ref="messageScroller" class="message-scroller">
            <div class="message-stack">
              <div v-if="chatStore.loading" class="panel-empty">Loading messages...</div>
              <div v-else-if="visibleMessages.length === 0" class="panel-empty">
                No messages yet. Start a conversation.
              </div>
              <article
                v-for="message in visibleMessages"
                :key="message.message_id || `${message.content}-${message.created_at}`"
                class="message-card"
                :class="{ outbound: message.direction === 'outbound' }"
              >
                <div class="message-meta">
                  <div class="message-source">{{ resolveMessageSource(message) }}</div>
                  <div class="message-state">
                    <span>{{ message.state || "sent" }}</span>
                    <span>{{ formatTimestamp(message.created_at) }}</span>
                  </div>
                </div>
                <div class="message-body">{{ message.content || "Attachment delivered." }}</div>
                <div v-if="message.attachments && message.attachments.length" class="attachment-list">
                  <div
                    v-for="attachment in message.attachments"
                    :key="`${attachment.file_id}-${attachment.name}`"
                    class="attachment-card"
                  >
                    <div v-if="attachment.category === 'image' && attachment.file_id" class="attachment-image">
                      <img :src="resolveAttachmentUrl(attachment)" :alt="attachment.name ?? 'image attachment'" />
                      <div class="attachment-meta">
                        <span>{{ attachment.name }}</span>
                        <span>{{ formatSize(attachment.size) }}</span>
                      </div>
                    </div>
                    <div v-else class="attachment-file">
                      <div>
                        <div class="attachment-name">{{ attachment.name }}</div>
                        <div class="attachment-type">{{ attachment.media_type || "File" }}</div>
                      </div>
                      <div class="attachment-size">{{ formatSize(attachment.size) }}</div>
                    </div>
                  </div>
                </div>
              </article>
            </div>
          </div>

          <div class="composer-panel">
            <div class="composer-top" :class="{ broadcast: composerScope === 'broadcast' }">
              <BaseSelect v-model="composerScope" label="Scope" :options="scopeOptions" />
              <BaseSelect
                v-if="composerScope !== 'broadcast'"
                v-model="composerTarget"
                :label="composerScope === 'topic' ? 'Topic' : 'Peer'"
                :options="composerTargetOptions"
              />
            </div>
            <div class="composer-grid">
              <textarea v-model="composerText" rows="3" class="composer-textarea" placeholder="Compose a message..."></textarea>
              <div class="composer-actions">
                <label class="attach-label">
                  <input type="file" class="hidden" multiple @change="handleAttachmentSelection" />
                  Attach files
                </label>
                <BaseButton icon-left="send" variant="primary" :disabled="sending" @click="sendMessage">Send</BaseButton>
              </div>
            </div>
            <div v-if="pendingAttachments.length" class="pending-attachments">
              <span v-for="attachment in pendingAttachments" :key="attachment.name" class="pending-pill">
                {{ attachment.name }} ({{ formatSize(attachment.size) }})
              </span>
            </div>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { nextTick } from "vue";
import { onBeforeUnmount } from "vue";
import { onMounted } from "vue";
import { ref } from "vue";
import { watch } from "vue";
import BaseButton from "../components/BaseButton.vue";
import BaseSelect from "../components/BaseSelect.vue";
import { endpoints } from "../api/endpoints";
import type { ChatAttachment } from "../api/types";
import type { ChatMessage } from "../api/types";
import type { WsMessage } from "../api/ws";
import { WsClient } from "../api/ws";
import { useChatStore } from "../stores/chat";
import { useConnectionStore } from "../stores/connection";
import { useToastStore } from "../stores/toasts";
import { useTopicsStore } from "../stores/topics";
import { useUsersStore } from "../stores/users";
import { useAppStore } from "../stores/app";
import { resolveIdentityLabel } from "../utils/identity";
import { isPresenceOnline } from "../utils/presence";

const chatStore = useChatStore();
const usersStore = useUsersStore();
const topicsStore = useTopicsStore();
const connectionStore = useConnectionStore();
const toastStore = useToastStore();
const appStore = useAppStore();

const searchQuery = ref("");
const activeScope = ref<"dm" | "topic" | "broadcast">("broadcast");
const activePeer = ref<string>("");
const activeTopic = ref<string>("");
const composerScope = ref<"dm" | "topic" | "broadcast">("broadcast");
const composerTarget = ref("");
const composerText = ref("");
const pendingAttachments = ref<File[]>([]);
const sending = ref(false);
const messageScroller = ref<HTMLDivElement | null>(null);
const directoryTab = ref<"peers" | "topics">("peers");

const MAX_ATTACHMENT_BYTES = 8 * 1024 * 1024;

const scopeOptions = [
  { value: "dm", label: "DM" },
  { value: "topic", label: "Topic" },
  { value: "broadcast", label: "Broadcast" }
];

const identityPresenceById = computed(() => {
  const map = new Map<string, { status?: string; lastSeen?: string }>();
  usersStore.identities.forEach((identity) => {
    if (!identity.id) {
      return;
    }
    const value = {
      status: identity.status,
      lastSeen: identity.last_seen
    };
    map.set(identity.id, value);
    map.set(identity.id.toLowerCase(), value);
  });
  return map;
});

const peers = computed(() => {
  const entries = usersStore.clients
    .filter((client) => client.id)
    .map((client) => {
      const clientId = client.id as string;
      const identityPresence =
        identityPresenceById.value.get(clientId) ?? identityPresenceById.value.get(clientId.toLowerCase());
      return {
        id: clientId,
        label: resolveIdentityLabel(client.display_name, clientId),
        online: isPresenceOnline({
          status: identityPresence?.status,
          lastSeenAt: client.last_seen_at ?? identityPresence?.lastSeen
        })
      };
    });
  entries.sort((a, b) => a.label.localeCompare(b.label));
  return entries;
});

const topics = computed(() =>
  topicsStore.topics.map((topic) => ({
    id: topic.id ?? "",
    label: topic.name?.trim() || "Untitled topic"
  }))
);

const filteredPeers = computed(() => {
  const query = searchQuery.value.trim().toLowerCase();
  if (!query) {
    return peers.value;
  }
  return peers.value.filter((peer) => peer.label.toLowerCase().includes(query));
});

const filteredTopics = computed(() => {
  const query = searchQuery.value.trim().toLowerCase();
  if (!query) {
    return topics.value;
  }
  return topics.value.filter((topic) => topic.label.toLowerCase().includes(query));
});

const activeLabel = computed(() => {
  if (activeScope.value === "broadcast") {
    return "All Hub Users";
  }
  if (activeScope.value === "dm") {
    const peer = peers.value.find((entry) => entry.id === activePeer.value);
    return peer?.label ?? "Direct Message";
  }
  const topic = topics.value.find((entry) => entry.id === activeTopic.value);
  return topic?.label ?? "Topic Channel";
});

const visibleMessages = computed(() => {
  if (activeScope.value === "broadcast") {
    return chatStore.messages.filter((message) => message.direction !== "outbound");
  }
  if (activeScope.value === "dm") {
    const peerId = activePeer.value;
    return chatStore.messages.filter((message) => {
      const source = message.source ?? "";
      const destination = message.destination ?? "";
      return source === peerId || destination === peerId;
    });
  }
  const topicId = activeTopic.value;
  return chatStore.messages.filter((message) => message.topic_id === topicId);
});

const scrollToLatest = async () => {
  await nextTick();
  if (messageScroller.value) {
    messageScroller.value.scrollTop = messageScroller.value.scrollHeight;
  }
};

const composerTargetOptions = computed(() => {
  if (composerScope.value === "topic") {
    return topics.value.map((topic) => ({ value: topic.id, label: topic.label }));
  }
  return peers.value.map((peer) => ({ value: peer.id, label: peer.label }));
});

const resolveAttachmentUrl = (attachment: ChatAttachment) => {
  if (!attachment.file_id) {
    return "";
  }
  const base =
    attachment.category === "image"
      ? `${endpoints.images}/${attachment.file_id}/raw`
      : `${endpoints.files}/${attachment.file_id}/raw`;
  return connectionStore.resolveUrl(base);
};

const resolveMessageSource = (message: ChatMessage) => {
  if (message.direction === "outbound") {
    return "Hub Operator";
  }
  const peer = peers.value.find((entry) => entry.id === message.source);
  return peer?.label ?? message.source ?? "Unknown";
};

const formatTimestamp = (value?: string) => {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  return date.toLocaleTimeString();
};

const formatSize = (size?: number) => {
  if (!size) {
    return "0B";
  }
  if (size < 1024) {
    return `${size}B`;
  }
  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)}KB`;
  }
  return `${(size / (1024 * 1024)).toFixed(1)}MB`;
};

const selectConversation = (scope: "dm" | "topic" | "broadcast", targetId?: string) => {
  activeScope.value = scope;
  composerScope.value = scope;
  if (scope === "dm") {
    activePeer.value = targetId ?? "";
    composerTarget.value = targetId ?? "";
    directoryTab.value = "peers";
  } else if (scope === "topic") {
    activeTopic.value = targetId ?? "";
    composerTarget.value = targetId ?? "";
    directoryTab.value = "topics";
  } else {
    activePeer.value = "";
    activeTopic.value = "";
    composerTarget.value = "";
  }
};

const handleAttachmentSelection = (event: Event) => {
  const target = event.target as HTMLInputElement;
  const files = Array.from(target.files ?? []);
  const accepted: File[] = [];
  for (const file of files) {
    if (file.size > MAX_ATTACHMENT_BYTES) {
      toastStore.push(`Attachment ${file.name} exceeds 8MB.`, "warning");
      continue;
    }
    accepted.push(file);
  }
  pendingAttachments.value = accepted;
  target.value = "";
};

const digestFile = async (file: File) => {
  const buffer = await file.arrayBuffer();
  const hashBuffer = await crypto.subtle.digest("SHA-256", buffer);
  return Array.from(new Uint8Array(hashBuffer))
    .map((value) => value.toString(16).padStart(2, "0"))
    .join("");
};

const sendMessage = async () => {
  if (sending.value) {
    return;
  }
  const scope = composerScope.value;
  if (scope !== "broadcast" && !composerTarget.value) {
    toastStore.push("Select a target for this message.", "warning");
    return;
  }
  const trimmed = composerText.value.trim();
  if (!trimmed && pendingAttachments.value.length === 0) {
    toastStore.push("Add a message or attachment first.", "warning");
    return;
  }
  const prefixedContent = trimmed
    ? appStore.appName
      ? `${appStore.appName} > ${trimmed}`
      : trimmed
    : "";
  sending.value = true;
  try {
    const fileIds: number[] = [];
    const imageIds: number[] = [];
    for (const file of pendingAttachments.value) {
      const category = file.type.startsWith("image/") ? "image" : "file";
      const sha256 = await digestFile(file);
      const attachment = await chatStore.uploadAttachment({
        category,
        file,
        sha256,
        topic_id: scope === "topic" ? composerTarget.value : undefined
      });
      if (attachment.file_id !== undefined) {
        if (category === "image") {
          imageIds.push(attachment.file_id);
        } else {
          fileIds.push(attachment.file_id);
        }
      }
    }
    await chatStore.sendMessage({
      content: prefixedContent,
      scope,
      destination: scope === "dm" ? composerTarget.value : undefined,
      topic_id: scope === "topic" ? composerTarget.value : undefined,
      file_ids: fileIds,
      image_ids: imageIds
    });
    composerText.value = "";
    pendingAttachments.value = [];
    toastStore.push("Message queued.", "success");
  } catch (error) {
    toastStore.push("Failed to send message.", "error");
  } finally {
    sending.value = false;
  }
};

const handleWsMessage = (message: WsMessage) => {
  if (message.type === "message.receive") {
    const entry = (message.data as { entry?: unknown }).entry ?? message.data;
    if (entry && typeof entry === "object") {
      chatStore.upsertMessage(fromWsMessage(entry as Record<string, unknown>));
    }
  }
};

const normalizeAttachment = (payload: Record<string, unknown>): ChatAttachment => ({
  file_id: (payload.FileID as number) ?? (payload.file_id as number),
  category: (payload.Category as string) ?? (payload.category as string),
  name: (payload.Name as string) ?? (payload.name as string),
  size: (payload.Size as number) ?? (payload.size as number),
  media_type: (payload.MediaType as string) ?? (payload.media_type as string)
});

const fromWsMessage = (payload: Record<string, unknown>): ChatMessage => ({
  message_id: payload.MessageID as string,
  direction: payload.Direction as string,
  scope: payload.Scope as string,
  state: payload.State as string,
  content: payload.Content as string,
  source: (payload.Source as string) ?? undefined,
  destination: (payload.Destination as string) ?? undefined,
  topic_id: (payload.TopicID as string) ?? undefined,
  attachments: Array.isArray(payload.Attachments)
    ? (payload.Attachments as Record<string, unknown>[]).map(normalizeAttachment)
    : [],
  created_at: payload.CreatedAt as string,
  updated_at: payload.UpdatedAt as string
});

let wsClient: WsClient | null = null;

onMounted(async () => {
  await Promise.all([usersStore.fetchUsers(), topicsStore.fetchTopics(), chatStore.fetchMessages()]);
  await scrollToLatest();
  wsClient = new WsClient("/messages/stream", handleWsMessage, () => {
    if (wsClient) {
      wsClient.send({
        type: "message.subscribe",
        ts: new Date().toISOString(),
        data: { follow: true }
      });
    }
  });
  wsClient.connect();
});

onBeforeUnmount(() => {
  wsClient?.close();
});

watch(composerScope, () => {
  composerTarget.value = "";
});

watch(
  () => visibleMessages.value.length,
  () => {
    scrollToLatest();
  }
);

watch(activeScope, () => {
  scrollToLatest();
});
</script>

<style scoped src="./styles/ChatPage.css"></style>


