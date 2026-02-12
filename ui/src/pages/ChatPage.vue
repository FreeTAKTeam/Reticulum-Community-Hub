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

<style scoped>
.chat-cosmos {
  --neon: #37f2ff;
  --neon-soft: rgba(55, 242, 255, 0.35);
  --panel-dark: rgba(4, 12, 22, 0.96);
  --panel-light: rgba(10, 30, 45, 0.94);
  --amber: #ffb35c;
  color: #dffcff;
  font-family: "Orbitron", "Rajdhani", "Barlow", sans-serif;
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.chat-shell {
  position: relative;
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 18px 20px 22px;
  border-radius: 18px;
  border: 1px solid rgba(55, 242, 255, 0.25);
  background: radial-gradient(circle at top, rgba(42, 210, 255, 0.12), transparent 56%),
    linear-gradient(145deg, rgba(5, 16, 28, 0.96), rgba(2, 6, 12, 0.98));
  box-shadow: 0 18px 55px rgba(1, 6, 12, 0.65), inset 0 0 0 1px rgba(55, 242, 255, 0.08);
  overflow: hidden;
}

.chat-shell::before {
  content: "";
  position: absolute;
  inset: 0;
  background: radial-gradient(circle at 1px 1px, rgba(55, 242, 255, 0.08) 1px, transparent 0) 0 0 / 18px 18px;
  opacity: 0.58;
  pointer-events: none;
}

.chat-top {
  position: relative;
  z-index: 1;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 14px;
}

.chat-title {
  font-size: 20px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #d4fbff;
  text-shadow: 0 0 12px rgba(55, 242, 255, 0.5);
}

.chat-subtitle {
  margin-top: 5px;
  font-family: "Rajdhani", "Barlow", sans-serif;
  font-size: 12px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: rgba(209, 251, 255, 0.7);
}

.chat-badges {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 10px;
}

.chat-badge {
  min-width: 120px;
  padding: 8px 10px;
  border: 1px solid rgba(55, 242, 255, 0.28);
  background: rgba(6, 18, 28, 0.78);
  clip-path: polygon(8px 0, 100% 0, calc(100% - 8px) 100%, 0 100%);
  display: grid;
  gap: 3px;
}

.chat-badge span {
  font-size: 10px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: rgba(206, 250, 255, 0.6);
}

.chat-badge strong {
  font-size: 12px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: #e8feff;
}

.chat-grid {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: minmax(270px, 330px) 1fr;
  gap: 16px;
  flex: 1;
  min-height: 0;
}

.panel {
  position: relative;
  padding: 16px;
  background: linear-gradient(145deg, var(--panel-light), var(--panel-dark));
  border: 1px solid rgba(55, 242, 255, 0.25);
  box-shadow: inset 0 0 0 1px rgba(55, 242, 255, 0.08), 0 12px 30px rgba(1, 6, 12, 0.6);
  clip-path: polygon(0 0, calc(100% - 24px) 0, 100% 24px, 100% 100%, 24px 100%, 0 calc(100% - 24px));
}

.panel::before {
  content: "";
  position: absolute;
  inset: 0;
  border: 1px solid rgba(55, 242, 255, 0.2);
  clip-path: polygon(
    1px 1px,
    calc(100% - 25px) 1px,
    calc(100% - 1px) 25px,
    calc(100% - 1px) calc(100% - 1px),
    25px calc(100% - 1px),
    1px calc(100% - 25px)
  );
  pointer-events: none;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 12px;
}

.panel-title {
  font-size: 15px;
  text-transform: uppercase;
  letter-spacing: 0.16em;
  color: #d1fbff;
}

.panel-subtitle {
  margin-top: 4px;
  font-family: "Rajdhani", "Barlow", sans-serif;
  font-size: 11px;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: rgba(209, 251, 255, 0.62);
}

.panel-chip {
  border: 1px solid var(--amber);
  color: var(--amber);
  font-size: 10px;
  padding: 4px 9px;
  border-radius: 999px;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  background: rgba(18, 24, 30, 0.62);
}

.chat-directory {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.directory-search {
  display: grid;
  gap: 6px;
}

.directory-search label {
  font-size: 10px;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: rgba(201, 248, 255, 0.64);
}

.directory-search input {
  width: 100%;
  background: rgba(6, 16, 25, 0.85);
  border: 1px solid rgba(55, 242, 255, 0.3);
  color: #d8fbff;
  border-radius: 10px;
  padding: 9px 12px;
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.directory-search input::placeholder {
  color: rgba(209, 251, 255, 0.42);
}

.directory-search input:focus {
  outline: none;
  border-color: rgba(55, 242, 255, 0.62);
  box-shadow: 0 0 14px rgba(55, 242, 255, 0.2);
}

.panel-tabs {
  margin-top: 12px;
  display: inline-flex;
  background: rgba(7, 18, 26, 0.8);
  border: 1px solid rgba(55, 242, 255, 0.25);
  border-radius: 999px;
  padding: 4px;
  gap: 4px;
}

.panel-tab {
  border: 1px solid transparent;
  background: transparent;
  color: rgba(209, 251, 255, 0.62);
  padding: 6px 14px;
  border-radius: 999px;
  text-transform: uppercase;
  letter-spacing: 0.16em;
  font-size: 11px;
  transition: all 0.2s ease;
}

.panel-tab.active {
  background: rgba(55, 242, 255, 0.12);
  border-color: rgba(55, 242, 255, 0.6);
  color: #e0feff;
  box-shadow: 0 0 14px rgba(55, 242, 255, 0.25);
}

.directory-list {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.chat-directory-scroll {
  min-height: 0;
  overflow-y: auto;
  max-height: none;
  flex: 1;
  padding-right: 6px;
  scrollbar-gutter: stable;
}

.directory-item {
  width: 100%;
  border: 1px solid rgba(55, 242, 255, 0.2);
  background: rgba(7, 18, 28, 0.62);
  color: rgba(213, 251, 255, 0.9);
  padding: 9px 10px;
  border-radius: 10px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  transition: all 0.2s ease;
}

.directory-item:hover {
  border-color: rgba(55, 242, 255, 0.4);
}

.directory-item.active {
  border-color: rgba(55, 242, 255, 0.68);
  background: rgba(55, 242, 255, 0.14);
  box-shadow: 0 0 16px rgba(55, 242, 255, 0.24);
}

.directory-item--broadcast {
  margin-top: 4px;
}

.directory-primary {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  font-size: 12px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.presence-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  border: 1px solid rgba(89, 106, 123, 0.55);
  background: rgba(7, 15, 24, 0.95);
  box-shadow: inset 0 0 3px rgba(1, 4, 8, 0.85), 0 0 6px rgba(18, 27, 38, 0.75);
}

.presence-dot.online {
  border-color: rgba(109, 255, 223, 0.92);
  background: #6dffdf;
  box-shadow: 0 0 10px rgba(109, 255, 223, 0.65);
}

.directory-tag {
  font-size: 10px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: rgba(206, 250, 255, 0.62);
}

.chat-main {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  gap: 12px;
  min-height: 0;
  overflow: hidden;
}

.conversation-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  border: 1px solid rgba(55, 242, 255, 0.2);
  border-radius: 10px;
  padding: 10px 12px;
  background: rgba(8, 20, 31, 0.72);
}

.conversation-state {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.scope-pill {
  border: 1px solid rgba(55, 242, 255, 0.32);
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 10px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: #d7fdff;
  background: rgba(8, 20, 30, 0.66);
}

.message-scroller {
  min-height: 0;
  overflow: hidden auto;
  border: 1px solid rgba(55, 242, 255, 0.22);
  border-radius: 12px;
  background: rgba(6, 16, 26, 0.78);
  padding: 12px;
  padding-right: 8px;
  scrollbar-gutter: stable;
  scrollbar-width: thin;
  scrollbar-color: rgba(44, 212, 230, 0.75) rgba(6, 18, 30, 0.92);
}

.message-scroller::-webkit-scrollbar {
  width: 10px;
}

.message-scroller::-webkit-scrollbar-track {
  background: linear-gradient(180deg, rgba(4, 12, 20, 0.95), rgba(6, 18, 30, 0.92));
  border: 1px solid rgba(56, 244, 255, 0.12);
  box-shadow: inset 0 0 10px rgba(3, 12, 18, 0.8);
}

.message-scroller::-webkit-scrollbar-thumb {
  background: linear-gradient(180deg, rgba(8, 36, 48, 0.95), rgba(44, 212, 230, 0.75));
  border: 1px solid rgba(56, 244, 255, 0.28);
  border-radius: 999px;
  box-shadow: 0 0 10px rgba(44, 212, 230, 0.35);
}

.message-scroller::-webkit-scrollbar-thumb:hover {
  background: linear-gradient(180deg, rgba(12, 50, 64, 0.98), rgba(70, 244, 255, 0.9));
}

.message-stack {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.panel-empty {
  border: 1px dashed rgba(55, 242, 255, 0.28);
  border-radius: 10px;
  padding: 14px;
  text-align: center;
  text-transform: uppercase;
  letter-spacing: 0.16em;
  font-size: 11px;
  color: rgba(209, 251, 255, 0.62);
}

.message-card {
  border: 1px solid rgba(55, 242, 255, 0.2);
  background: rgba(8, 20, 30, 0.74);
  border-radius: 10px;
  padding: 10px;
}

.message-card.outbound {
  border-color: rgba(255, 179, 92, 0.45);
  background: rgba(38, 22, 10, 0.4);
}

.message-meta {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}

.message-source {
  font-size: 10px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: rgba(209, 251, 255, 0.72);
}

.message-state {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 10px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: rgba(209, 251, 255, 0.56);
}

.message-body {
  margin-top: 8px;
  white-space: pre-wrap;
  font-family: "Rajdhani", "Barlow", sans-serif;
  font-size: 14px;
  color: #e5fcff;
}

.attachment-list {
  margin-top: 10px;
  display: grid;
  gap: 8px;
}

.attachment-card {
  border: 1px solid rgba(55, 242, 255, 0.18);
  border-radius: 9px;
  background: rgba(6, 16, 25, 0.75);
  padding: 8px;
}

.attachment-image img {
  width: 100%;
  max-height: 220px;
  object-fit: cover;
  border-radius: 8px;
  border: 1px solid rgba(55, 242, 255, 0.2);
}

.attachment-meta {
  margin-top: 8px;
  display: flex;
  justify-content: space-between;
  gap: 10px;
  font-size: 11px;
  color: rgba(213, 251, 255, 0.8);
}

.attachment-file {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: center;
}

.attachment-name {
  font-size: 12px;
  color: #e6feff;
}

.attachment-type {
  font-size: 11px;
  color: rgba(209, 251, 255, 0.58);
}

.attachment-size {
  font-size: 10px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: rgba(209, 251, 255, 0.64);
}

.composer-panel {
  border: 1px solid rgba(55, 242, 255, 0.24);
  border-radius: 12px;
  background: rgba(7, 18, 28, 0.76);
  padding: 12px;
  display: grid;
  gap: 10px;
}

.composer-top {
  display: grid;
  grid-template-columns: 160px 1fr;
  gap: 10px;
}

.composer-top.broadcast {
  grid-template-columns: 160px;
}

.composer-grid {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 10px;
}

.composer-textarea {
  width: 100%;
  min-height: 110px;
  resize: vertical;
  border: 1px solid rgba(55, 242, 255, 0.3);
  border-radius: 10px;
  background: linear-gradient(180deg, rgba(8, 22, 34, 0.95), rgba(5, 15, 24, 0.98));
  color: #dffcff;
  padding: 11px;
  font-family: "Rajdhani", "Barlow", sans-serif;
  font-size: 14px;
  line-height: 1.4;
}

.composer-textarea:focus {
  outline: none;
  border-color: rgba(55, 242, 255, 0.66);
  box-shadow: 0 0 16px rgba(55, 242, 255, 0.22);
}

.composer-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  justify-content: flex-start;
}

.attach-label {
  cursor: pointer;
  border: 1px solid rgba(55, 242, 255, 0.3);
  background: rgba(8, 20, 31, 0.8);
  color: rgba(213, 251, 255, 0.76);
  border-radius: 9px;
  padding: 9px 12px;
  font-size: 11px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  text-align: center;
}

.pending-attachments {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.pending-pill {
  border: 1px solid rgba(55, 242, 255, 0.28);
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 10px;
  letter-spacing: 0.1em;
  color: rgba(225, 253, 255, 0.84);
  background: rgba(8, 20, 30, 0.68);
}

:deep(.chat-cosmos .cui-btn) {
  background: linear-gradient(135deg, rgba(35, 130, 160, 0.45), rgba(6, 18, 28, 0.92));
  border: 1px solid rgba(55, 242, 255, 0.45);
  color: #e5feff;
  text-transform: uppercase;
  letter-spacing: 0.18em;
  font-size: 10px;
  padding: 6px 12px;
  box-shadow: 0 0 12px rgba(55, 242, 255, 0.15);
}

:deep(.chat-cosmos .cui-btn--secondary) {
  background: linear-gradient(135deg, rgba(14, 44, 60, 0.85), rgba(6, 14, 22, 0.92));
}

:deep(.chat-cosmos .cui-combobox__label) {
  letter-spacing: 0.16em;
  color: rgba(209, 251, 255, 0.64);
}

@media (max-width: 1100px) {
  .chat-grid {
    grid-template-columns: 1fr;
    grid-template-rows: minmax(180px, 0.42fr) minmax(0, 1fr);
    height: 100%;
  }
}

@media (max-width: 760px) {
  .chat-top {
    flex-direction: column;
  }

  .chat-badges {
    justify-content: flex-start;
  }

  .conversation-head {
    flex-direction: column;
    align-items: flex-start;
  }

  .composer-top,
  .composer-top.broadcast,
  .composer-grid {
    grid-template-columns: 1fr;
  }

  .composer-actions {
    flex-direction: row;
    flex-wrap: wrap;
  }

  .panel-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .panel-tabs {
    align-self: flex-start;
  }
}
</style>
