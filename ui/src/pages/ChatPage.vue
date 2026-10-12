<template>
  <div class="chat-cosmos">
    <div class="chat-shell">
      <p v-if="usersStore.errors.clients" role="status" class="panel-empty">Unable to load chat clients: {{ usersStore.errors.clients }}</p>
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
              <BaseButton variant="secondary" icon-left="refresh" @click="refreshHistory">Refresh</BaseButton>
            </div>
          </div>

          <div class="chat-history-window">
            <div class="history-controls">
              <BaseButton variant="secondary" :disabled="chatStore.loading || !chatStore.nextCursor" @click="loadOlder">Older messages</BaseButton>
              <BaseButton v-if="chatStore.viewingHistory" variant="secondary" @click="refreshHistory">Latest messages</BaseButton>
              <span v-if="!chatStore.paging" role="status">This backend does not support older history pages.</span>
              <span v-if="chatStore.error" role="alert">{{ chatStore.error }}</span>
            </div>
            <ChatMessageList ref="messageList" :messages="visibleMessages" :loading="chatStore.loading" :source-label="resolveMessageSource" @download="downloadAttachment" />
            <output v-if="development" class="chat-diagnostics" aria-label="Chat cache diagnostics">{{ JSON.stringify(chatStore.diagnostics) }}</output>
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
import { onBeforeUnmount } from "vue";
import { onMounted } from "vue";
import { ref } from "vue";
import { watch } from "vue";
import BaseButton from "../components/BaseButton.vue";
import BaseSelect from "../components/BaseSelect.vue";
import ChatMessageList from "../components/chat/ChatMessageList.vue";
import { decodeChatMessage } from "../api/chat";
import { endpoints } from "../api/endpoints";
import { getBlob } from "../api/client";
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
const activeScope = ref<"dm" | "topic" | "broadcast">(chatStore.conversation.scope);
const activePeer = ref<string>(chatStore.conversation.scope === "dm" ? chatStore.conversation.target ?? "" : "");
const activeTopic = ref<string>(chatStore.conversation.scope === "topic" ? chatStore.conversation.target ?? "" : "");
const composerScope = ref<"dm" | "topic" | "broadcast">(chatStore.conversation.scope);
const composerTarget = ref(chatStore.conversation.target ?? "");
const composerText = ref("");
const pendingAttachments = ref<File[]>([]);
const sending = ref(false);
let sendGeneration = 0;
const messageList = ref<InstanceType<typeof ChatMessageList> | null>(null);
const development = import.meta.env.DEV;
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

const visibleMessages = computed(() => chatStore.visibleMessages);
const scrollToLatest = () => messageList.value?.scrollToLatest();
const refreshHistory = async () => {
  try { await chatStore.fetchMessages(); await scrollToLatest(); }
  catch (error) { if (!(error instanceof DOMException && error.name === "AbortError")) { toastStore.push(chatStore.error || "Unable to load history.", "error"); } }
};
const loadOlder = async () => {
  try { await chatStore.loadOlder(); await messageList.value?.scrollToStart(); }
  catch (error) { if (!(error instanceof DOMException && error.name === "AbortError")) { toastStore.push(chatStore.error || "Unable to load older history.", "error"); } }
};

const composerTargetOptions = computed(() => {
  if (composerScope.value === "topic") {
    return topics.value.map((topic) => ({ value: topic.id, label: topic.label }));
  }
  return peers.value.map((peer) => ({ value: peer.id, label: peer.label }));
});

const attachmentPath = (attachment: ChatAttachment) => attachment.file_id
  ? `${attachment.category === "image" ? endpoints.images : endpoints.files}/${attachment.file_id}/raw`
  : "";
const downloadAttachment = async (attachment: ChatAttachment) => {
  const path = attachmentPath(attachment);
  if (!path) { return; }
  try {
    const blob = await getBlob(path);
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = attachment.name || "attachment";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  } catch (error) {
    toastStore.push(error instanceof Error ? error.message : "Attachment download failed.", "error");
  }
};

const resolveMessageSource = (message: ChatMessage) => {
  if (message.direction === "outbound") {
    return "Hub Operator";
  }
  const peer = peers.value.find((entry) => entry.id === message.source);
  return peer?.label ?? message.source ?? "Unknown";
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
  const target = composerTarget.value;
  if (scope !== "broadcast" && !target) {
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
  const sendIdentity = connectionStore.requestIdentity;
  const capturedGeneration = sendGeneration;
  const assertSendCurrent = () => {
    if (disposed || sendGeneration !== capturedGeneration || connectionStore.requestIdentity !== sendIdentity) { throw new DOMException("Chat backend changed", "AbortError"); }
  };
  try {
    const fileIds: number[] = [];
    const imageIds: number[] = [];
    for (const file of pendingAttachments.value) {
      const category = file.type.startsWith("image/") ? "image" : "file";
      const sha256 = await digestFile(file);
      assertSendCurrent();
      const attachment = await chatStore.uploadAttachment({
        category,
        file,
        sha256,
        topic_id: scope === "topic" ? target : undefined
      });
      assertSendCurrent();
      if (attachment.file_id !== undefined) {
        if (category === "image") {
          imageIds.push(attachment.file_id);
        } else {
          fileIds.push(attachment.file_id);
        }
      }
    }
    assertSendCurrent();
    await chatStore.sendMessage({
      content: prefixedContent,
      scope,
      destination: scope === "dm" ? target : undefined,
      topic_id: scope === "topic" ? target : undefined,
      file_ids: fileIds,
      image_ids: imageIds
    });
    assertSendCurrent();
    selectConversation(scope, scope === "broadcast" ? undefined : target);
    composerText.value = "";
    pendingAttachments.value = [];
    toastStore.push("Message queued.", "success");
  } catch (error) {
    toastStore.push(error instanceof Error ? error.message : "Failed to send message.", "error");
  } finally {
    if (sendGeneration === capturedGeneration) { sending.value = false; }
  }
};

const handleWsMessage = (message: WsMessage) => {
  if (message.type !== "message.receive") { return; }
  try {
    const data = message.data;
    const entry = data && typeof data === "object" && "entry" in data ? data.entry : data;
    chatStore.upsertMessage(decodeChatMessage(entry));
  } catch (error) { toastStore.push(error instanceof Error ? error.message : "Invalid chat event.", "error"); }
};

let wsClient: WsClient | null = null;
let disposed = false;

const openStream = () => {
  wsClient?.close();
  wsClient = new WsClient("/messages/stream", handleWsMessage, () => {
    wsClient?.send({ type: "message.subscribe", ts: new Date().toISOString(), data: { follow: true } });
  });
  wsClient.connect();
};

onMounted(() => {
  chatStore.start();
  openStream();
  const load = async (work: () => Promise<unknown>, label: string) => {
    try { await work(); }
    catch (error) {
      if (!disposed) {
        console.warn(`Unable to load ${label}`, error);
        toastStore.push(`Unable to load ${label}`, "danger");
      }
    }
  };
  void load(() => usersStore.fetchClients(), "chat clients");
  void load(() => topicsStore.fetchTopics(), "chat topics");
  void load(async () => {
    await chatStore.fetchMessages();
    if (!disposed) { await scrollToLatest(); }
  }, "chat history");
});

onBeforeUnmount(() => {
  sendGeneration++;
  disposed = true;
  wsClient?.close();
  chatStore.stop();
});

watch(composerScope, (scope) => {
  if (scope === activeScope.value) {
    composerTarget.value =
      scope === "dm" ? activePeer.value : scope === "topic" ? activeTopic.value : "";
    return;
  }
  composerTarget.value = "";
});

watch(() => [activeScope.value, activePeer.value, activeTopic.value], async () => {
  const target = activeScope.value === "dm" ? activePeer.value : activeScope.value === "topic" ? activeTopic.value : undefined;
  try { await chatStore.fetchConversation({ scope: activeScope.value, target }); await scrollToLatest(); }
  catch (error) { if (!(error instanceof DOMException && error.name === "AbortError")) { toastStore.push(chatStore.error || "Unable to load conversation.", "error"); } }
});
watch(() => connectionStore.requestIdentity, () => {
  sendGeneration++;
  activeScope.value = "broadcast"; activePeer.value = ""; activeTopic.value = "";
  wsClient?.close();
  composerText.value = ""; pendingAttachments.value = []; sending.value = false;
  if (connectionStore.isAuthenticated) { chatStore.start(); openStream(); void refreshHistory(); }
}, { flush: "sync" });
watch(() => connectionStore.isAuthenticated, (authenticated) => {
  if (!authenticated) { sendGeneration++; wsClient?.close(); chatStore.stop(); composerText.value = ""; pendingAttachments.value = []; sending.value = false; }
  else if (!disposed) { chatStore.start(); openStream(); void refreshHistory(); }
}, { flush: "sync" });
</script>

<style scoped src="./styles/ChatPage.css"></style>
