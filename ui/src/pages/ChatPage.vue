<template>
  <div class="grid gap-6 xl:grid-cols-[320px_1fr]">
    <section class="space-y-4">
      <BaseCard title="Operators">
        <BaseInput v-model="searchQuery" label="Search" placeholder="Filter peers or topics" />
        <div class="mt-4 space-y-3">
          <div class="text-[11px] uppercase tracking-[0.2em] text-rth-muted">Peers</div>
          <div class="space-y-2">
            <button
              v-for="peer in filteredPeers"
              :key="peer.id"
              class="flex w-full items-center justify-between rounded border border-rth-border bg-rth-panel-muted px-3 py-2 text-left text-xs transition hover:border-rth-accent"
              :class="peer.id === activePeer ? 'border-rth-accent shadow-[0_0_12px_rgba(0,180,255,0.35)]' : ''"
              @click="selectConversation('dm', peer.id)"
            >
              <span class="truncate">
                <span class="mr-2 inline-flex h-2 w-2 rounded-full" :class="peer.online ? 'bg-emerald-400' : 'bg-slate-500'" />
                {{ peer.label }}
              </span>
              <span class="text-[10px] uppercase tracking-[0.2em] text-rth-muted">DM</span>
            </button>
          </div>
          <div class="pt-2 text-[11px] uppercase tracking-[0.2em] text-rth-muted">Topics</div>
          <div class="space-y-2">
            <button
              v-for="topic in filteredTopics"
              :key="topic.id"
              class="flex w-full items-center justify-between rounded border border-rth-border bg-rth-panel-muted px-3 py-2 text-left text-xs transition hover:border-rth-accent"
              :class="topic.id === activeTopic ? 'border-rth-accent shadow-[0_0_12px_rgba(0,180,255,0.35)]' : ''"
              @click="selectConversation('topic', topic.id)"
            >
              <span class="truncate">{{ topic.label }}</span>
              <span class="text-[10px] uppercase tracking-[0.2em] text-rth-muted">Topic</span>
            </button>
          </div>
          <div class="pt-2">
            <button
              class="flex w-full items-center justify-between rounded border border-rth-border bg-rth-panel-muted px-3 py-2 text-left text-xs transition hover:border-rth-accent"
              :class="activeScope === 'broadcast' ? 'border-rth-accent shadow-[0_0_12px_rgba(0,180,255,0.35)]' : ''"
              @click="selectConversation('broadcast')"
            >
              <span class="truncate">Broadcast</span>
              <span class="text-[10px] uppercase tracking-[0.2em] text-rth-muted">All</span>
            </button>
          </div>
        </div>
      </BaseCard>
    </section>

    <section class="flex flex-col gap-4">
      <div class="rounded border border-rth-border bg-rth-panel p-4 shadow-[0_0_24px_rgba(0,180,255,0.12)]">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div>
            <div class="text-xs uppercase tracking-[0.2em] text-rth-muted">Conversation</div>
            <div class="text-lg font-semibold">{{ activeLabel }}</div>
          </div>
          <div class="flex items-center gap-2 text-xs text-rth-muted">
            <span class="rounded border border-rth-border px-2 py-1 uppercase tracking-[0.2em]">
              {{ activeScope.toUpperCase() }}
            </span>
            <span class="text-[10px] uppercase tracking-[0.2em] text-rth-muted">Delivery state inline</span>
          </div>
        </div>
      </div>

      <div class="flex-1 rounded border border-rth-border bg-rth-panel/80 p-4 shadow-[0_0_32px_rgba(0,180,255,0.08)]">
        <div class="flex h-full flex-col gap-4 overflow-y-auto pr-2">
          <div v-if="chatStore.loading" class="text-xs text-rth-muted">Loading messages...</div>
          <div v-else-if="visibleMessages.length === 0" class="text-xs text-rth-muted">
            No messages yet. Start a conversation.
          </div>
          <div
            v-for="message in visibleMessages"
            :key="message.message_id || `${message.content}-${message.created_at}`"
            class="rounded border border-rth-border bg-rth-panel-muted p-3"
          >
            <div class="flex flex-wrap items-center justify-between gap-2">
              <div class="text-xs uppercase tracking-[0.2em] text-rth-muted">
                {{ resolveMessageSource(message) }}
              </div>
              <div class="flex items-center gap-2 text-[11px] uppercase tracking-[0.2em] text-rth-muted">
                <span>{{ message.state || "sent" }}</span>
                <span>{{ formatTimestamp(message.created_at) }}</span>
              </div>
            </div>
            <div class="mt-2 whitespace-pre-wrap text-sm text-rth-text">
              {{ message.content || "Attachment delivered." }}
            </div>
            <div v-if="message.attachments && message.attachments.length" class="mt-3 space-y-2">
              <div
                v-for="attachment in message.attachments"
                :key="`${attachment.file_id}-${attachment.name}`"
                class="rounded border border-rth-border bg-rth-panel p-2 text-xs text-rth-muted"
              >
                <div v-if="attachment.category === 'image' && attachment.file_id" class="space-y-2">
                  <img
                    :src="resolveAttachmentUrl(attachment)"
                    :alt="attachment.name ?? 'image attachment'"
                    class="max-h-48 w-full rounded border border-rth-border object-cover"
                  />
                  <div class="flex flex-wrap items-center justify-between">
                    <span>{{ attachment.name }}</span>
                    <span>{{ formatSize(attachment.size) }}</span>
                  </div>
                </div>
                <div v-else class="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <div class="font-semibold text-rth-text">{{ attachment.name }}</div>
                    <div>{{ attachment.media_type || "File" }}</div>
                  </div>
                  <div class="text-[11px] uppercase tracking-[0.2em]">{{ formatSize(attachment.size) }}</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="rounded border border-rth-border bg-rth-panel p-4 shadow-[0_0_24px_rgba(0,180,255,0.12)]">
        <div class="grid gap-3 md:grid-cols-[140px_1fr_1fr]">
          <BaseSelect v-model="composerScope" label="Scope" :options="scopeOptions" />
          <BaseSelect
            v-if="composerScope !== 'broadcast'"
            v-model="composerTarget"
            :label="composerScope === 'topic' ? 'Topic' : 'Peer'"
            :options="composerTargetOptions"
          />
          <div class="flex items-end justify-end md:col-span-1" :class="composerScope === 'broadcast' ? 'md:col-span-2' : ''">
            <BaseButton variant="secondary" icon-left="refresh" @click="chatStore.fetchMessages()">Refresh</BaseButton>
          </div>
        </div>
        <div class="mt-4 grid gap-3 md:grid-cols-[1fr_auto]">
          <textarea
            v-model="composerText"
            rows="3"
            class="w-full rounded border border-rth-border bg-rth-panel-muted p-3 text-sm text-rth-text focus:border-rth-accent focus:outline-none"
            placeholder="Compose a message..."
          ></textarea>
          <div class="flex flex-col gap-2">
            <label class="cursor-pointer rounded border border-rth-border bg-rth-panel-muted px-3 py-2 text-xs text-rth-muted">
              <input type="file" class="hidden" multiple @change="handleAttachmentSelection" />
              Attach files
            </label>
            <BaseButton icon-left="send" variant="primary" :disabled="sending" @click="sendMessage">
              Send
            </BaseButton>
          </div>
        </div>
        <div v-if="pendingAttachments.length" class="mt-3 flex flex-wrap gap-2 text-xs text-rth-muted">
          <span
            v-for="attachment in pendingAttachments"
            :key="attachment.name"
            class="rounded border border-rth-border bg-rth-panel-muted px-2 py-1"
          >
            {{ attachment.name }} ({{ formatSize(attachment.size) }})
          </span>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { onBeforeUnmount } from "vue";
import { onMounted } from "vue";
import { ref } from "vue";
import { watch } from "vue";
import BaseButton from "../components/BaseButton.vue";
import BaseCard from "../components/BaseCard.vue";
import BaseInput from "../components/BaseInput.vue";
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
import { resolveIdentityLabel } from "../utils/identity";

const chatStore = useChatStore();
const usersStore = useUsersStore();
const topicsStore = useTopicsStore();
const connectionStore = useConnectionStore();
const toastStore = useToastStore();

const searchQuery = ref("");
const activeScope = ref<"dm" | "topic" | "broadcast">("broadcast");
const activePeer = ref<string>("");
const activeTopic = ref<string>("");
const composerScope = ref<"dm" | "topic" | "broadcast">("broadcast");
const composerTarget = ref("");
const composerText = ref("");
const pendingAttachments = ref<File[]>([]);
const sending = ref(false);

const MAX_ATTACHMENT_BYTES = 8 * 1024 * 1024;

const scopeOptions = [
  { value: "dm", label: "DM" },
  { value: "topic", label: "Topic" },
  { value: "broadcast", label: "Broadcast" }
];

const peers = computed(() => {
  const onlineIds = new Set(usersStore.clients.map((client) => client.id).filter(Boolean) as string[]);
  const entries = usersStore.identities.map((identity) => ({
    id: identity.id ?? "",
    label: resolveIdentityLabel(identity.display_name, identity.id),
    online: onlineIds.has(identity.id ?? "")
  }));
  entries.sort((a, b) => Number(b.online) - Number(a.online));
  return entries;
});

const topics = computed(() =>
  topicsStore.topics.map((topic) => ({
    id: topic.id ?? "",
    label: topic.name ? `${topic.name} (${topic.id})` : topic.id ?? "Unknown"
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
    return chatStore.messages.filter((message) => message.scope === "broadcast");
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
  } else if (scope === "topic") {
    activeTopic.value = targetId ?? "";
    composerTarget.value = targetId ?? "";
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
      content: trimmed,
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
</script>
