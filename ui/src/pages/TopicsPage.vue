<template>
  <div class="topics-registry">
    <div class="registry-shell">
      <header class="registry-top">
        <div class="registry-title">Topic Registry</div>
        <div class="registry-status">
          <OnlineHelpLauncher />
          <span class="cui-status-pill" :class="connectionClass">{{ connectionLabel }}</span>
          <span class="cui-status-pill" :class="wsClass">{{ wsLabel }}</span>
          <span class="status-url">{{ baseUrl }}</span>
        </div>
      </header>

      <div class="registry-grid">
        <aside class="panel registry-tree">
          <div class="panel-header">
            <div>
              <div class="panel-title">Topic Hierarchy Tree</div>
              <div class="panel-subtitle">Focus Node</div>
            </div>
            <div class="panel-chip">{{ treeEntries.length }} nodes</div>
          </div>
          <div class="tree-search">
            <input v-model="treeFilter" type="text" placeholder="Filter or jump" />
          </div>
          <div class="tree-list">
            <button
              v-for="entry in filteredTreeEntries"
              :key="entry.path"
              class="tree-item"
              :class="{ active: selectedBranch === entry.path }"
              :style="{ '--depth': entry.depth }"
              type="button"
              @click="selectBranch(entry.path)"
            >
              <span class="tree-dot" aria-hidden="true"></span>
              <span class="tree-label">{{ entry.name }}</span>
              <span class="tree-count">{{ entry.count }}</span>
            </button>
            <div v-if="filteredTreeEntries.length === 0" class="tree-empty">No topics match the filter.</div>
          </div>
        </aside>

        <section class="panel registry-main">
          <div class="panel-header">
            <div>
              <div class="panel-title">Branch: {{ selectedBranch || "All" }}</div>
            </div>
            <div class="panel-tabs">
              <button class="panel-tab" :class="{ active: activeTab === 'topics' }" type="button" @click="activeTab = 'topics'">
                Topics
              </button>
              <button
                class="panel-tab"
                :class="{ active: activeTab === 'subscribers' }"
                type="button"
                @click="activeTab = 'subscribers'"
              >
                Subscribers
              </button>
            </div>
          </div>

          <LoadingSkeleton v-if="activeTab === 'topics' && topicsStore.loading" />
          <LoadingSkeleton v-else-if="activeTab === 'subscribers' && subscribersStore.loading" />
          <div v-else>
            <div v-if="activeTab === 'topics'" class="card-grid">
              <div v-for="topic in pagedTopics" :key="topic.id" class="registry-card cui-panel">
                <div class="registry-card-header">
                  <div>
                    <div class="registry-card-title">{{ topicTitle(topic) }}</div>
                    <div class="registry-card-subtitle mono">{{ topicPathLabel(topic) }}</div>
                  </div>
                </div>
                <div class="registry-card-meta">
                  <div><span>Topic ID</span><span class="mono">{{ topic.id || "Pending" }}</span></div>
                  <div><span>Subscribers</span><span>{{ subscriberCountForTopic(topic.id) }}</span></div>
                  <div class="registry-card-desc">
                    <span>Description</span>
                    <span>{{ topic.description || "No description on record." }}</span>
                  </div>
                </div>
                <div class="registry-card-actions">
                  <BaseButton variant="secondary" icon-left="edit" @click="openTopicModal(topic)">Edit</BaseButton>
                  <BaseButton variant="danger" icon-left="trash" @click="removeTopic(topic.id)">Delete</BaseButton>
                </div>
              </div>
              <div v-if="pagedTopics.length === 0" class="panel-empty">No topics in this branch.</div>
              <BasePagination
                v-if="filteredTopics.length"
                v-model:page="topicsPage"
                :page-size="topicsPageSize"
                :total="filteredTopics.length"
              />
            </div>

            <div v-else class="card-grid">
              <div v-for="subscriber in pagedSubscribers" :key="subscriber.id" class="registry-card cui-panel">
                <div class="registry-card-header">
                  <div>
                    <div class="registry-card-title">{{ resolveSourceName(subscriber) || "Unknown source" }}</div>
                    <div class="registry-card-subtitle">{{ resolveTopicLabel(subscriber.topic_id) }}</div>
                  </div>
                  <div class="registry-card-tag">Route</div>
                </div>
                <div class="registry-card-meta">
                  <div><span>Destination</span><span class="mono">{{ subscriber.destination || "Unknown" }}</span></div>
                  <div><span>Reject Tests</span><span>{{ subscriber.reject_tests ? "True" : "False" }}</span></div>
                  <div class="registry-card-desc">
                    <span>Subscriber ID</span>
                    <span class="mono">{{ subscriber.id || "Pending" }}</span>
                  </div>
                </div>
                <div class="registry-card-actions">
                  <BaseButton variant="secondary" icon-left="edit" @click="openSubscriberModal(subscriber)">Edit</BaseButton>
                  <BaseButton variant="danger" icon-left="trash" @click="removeSubscriber(subscriber.id)">Delete</BaseButton>
                </div>
              </div>
              <div v-if="pagedSubscribers.length === 0" class="panel-empty">No subscribers in this branch.</div>
              <BasePagination
                v-if="filteredSubscribers.length"
                v-model:page="subscribersPage"
                :page-size="subscribersPageSize"
                :total="filteredSubscribers.length"
              />
            </div>
          </div>

          <div class="panel-actions">
            <BaseButton v-if="activeTab === 'topics'" icon-left="plus" @click="openTopicModal(null)">New Topic</BaseButton>
            <BaseButton v-if="activeTab === 'subscribers'" icon-left="plus" @click="openSubscriberModal(null)">Add Subscriber</BaseButton>
            <BaseButton
              variant="secondary"
              icon-left="refresh"
              @click="activeTab === 'topics' ? topicsStore.fetchTopics() : subscribersStore.fetchSubscribers()"
            >
              Refresh
            </BaseButton>
          </div>
        </section>
      </div>
    </div>

    <BaseModal :open="topicModalOpen" title="Topic" @close="topicModalOpen = false">
      <div class="space-y-3">
        <BaseInput v-model="topicDraft.name" label="Name" />
        <BaseInput v-model="topicDraft.path" label="Path" />
        <BaseInput v-model="topicDraft.description" label="Description" />
        <BaseButton icon-left="check" variant="success" @click="saveTopic">Save Topic</BaseButton>
      </div>
    </BaseModal>

    <BaseModal :open="subscriberModalOpen" title="Subscriber" @close="subscriberModalOpen = false">
      <div class="space-y-3">
        <BaseSelect v-model="subscriberDraft.topic_id" label="Topic ID" :options="topicOptions" />
        <BaseSelect v-model="subscriberDraft.destination" label="Destination" :options="destinationOptions" />
        <BaseInput v-model="subscriberDraft.reject_tests" label="Reject Tests (true/false)" />
        <BaseButton icon-left="check" variant="success" @click="saveSubscriber">Save Subscriber</BaseButton>
      </div>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, watch } from "vue";
import { ref } from "vue";
import BaseButton from "../components/BaseButton.vue";
import BaseInput from "../components/BaseInput.vue";
import BaseModal from "../components/BaseModal.vue";
import BaseSelect from "../components/BaseSelect.vue";
import BasePagination from "../components/BasePagination.vue";
import LoadingSkeleton from "../components/LoadingSkeleton.vue";
import OnlineHelpLauncher from "../components/OnlineHelpLauncher.vue";
import type { ApiError } from "../api/client";
import type { Subscriber } from "../api/types";
import type { Topic } from "../api/types";
import { useConnectionStore } from "../stores/connection";
import { useSubscribersStore } from "../stores/subscribers";
import { useTopicsStore } from "../stores/topics";
import { useToastStore } from "../stores/toasts";
import { useUsersStore } from "../stores/users";
import { resolveIdentityLabel } from "../utils/identity";

type TreeEntry = {
  name: string;
  path: string;
  depth: number;
  count: number;
};

const topicsStore = useTopicsStore();
const subscribersStore = useSubscribersStore();
const connectionStore = useConnectionStore();
const usersStore = useUsersStore();
const toastStore = useToastStore();

const topicModalOpen = ref(false);
const subscriberModalOpen = ref(false);
const topicDraft = ref<Topic>({ name: "", path: "", description: "" });
const subscriberDraft = ref<Subscriber>({ topic_id: "", destination: "", reject_tests: false });
const activeTab = ref<"topics" | "subscribers">("topics");
const topicsPage = ref(1);
const subscribersPage = ref(1);
const topicsPageSize = 6;
const subscribersPageSize = 6;
const treeFilter = ref("");
const selectedBranch = ref("");

const normalizeText = (value?: string) => {
  if (!value) {
    return undefined;
  }
  const trimmed = value.trim();
  return trimmed.length ? trimmed : undefined;
};

const splitTopicPath = (value: string) => {
  const trimmed = value.trim();
  if (!trimmed) {
    return [] as string[];
  }
  if (trimmed.includes("/")) {
    return trimmed.split("/").map((segment) => segment.trim()).filter(Boolean);
  }
  if (trimmed.includes(".")) {
    return trimmed.split(".").map((segment) => segment.trim()).filter(Boolean);
  }
  if (trimmed.includes(":")) {
    return trimmed.split(":").map((segment) => segment.trim()).filter(Boolean);
  }
  return [trimmed];
};

const topicTitle = (topic: Topic) =>
  normalizeText(topic.name) ?? normalizeText(topic.path) ?? normalizeText(topic.id) ?? "Untitled";

const topicPathLabel = (topic: Topic) =>
  normalizeText(topic.path) ?? normalizeText(topic.name) ?? normalizeText(topic.id) ?? "Unknown";

const topicKey = (topic: Topic) => {
  const label = topicPathLabel(topic);
  const segments = splitTopicPath(label);
  return segments.join(".");
};

const topicKeyById = computed(() => {
  const map = new Map<string, string>();
  topicsStore.topics.forEach((topic) => {
    if (topic.id) {
      map.set(topic.id, topicKey(topic));
    }
  });
  return map;
});

const topicLabelById = computed(() => {
  const map = new Map<string, string>();
  topicsStore.topics.forEach((topic) => {
    if (topic.id) {
      map.set(topic.id, topicTitle(topic));
    }
  });
  return map;
});

const subscriberCountByTopicId = computed(() => {
  const map = new Map<string, number>();
  subscribersStore.subscribers.forEach((subscriber) => {
    if (!subscriber.topic_id) {
      return;
    }
    map.set(subscriber.topic_id, (map.get(subscriber.topic_id) ?? 0) + 1);
  });
  return map;
});

const subscriberCountForTopic = (topicId?: string) => {
  if (!topicId) {
    return 0;
  }
  return subscriberCountByTopicId.value.get(topicId) ?? 0;
};

const treeEntries = computed<TreeEntry[]>(() => {
  const map = new Map<string, TreeEntry>();
  topicsStore.topics.forEach((topic) => {
    const key = topicKey(topic);
    if (!key) {
      return;
    }
    const segments = key.split(".");
    let path = "";
    segments.forEach((segment, index) => {
      path = path ? `${path}.${segment}` : segment;
      const existing = map.get(path);
      if (existing) {
        existing.count += 1;
      } else {
        map.set(path, { name: segment, path, depth: index, count: 1 });
      }
    });
  });
  return Array.from(map.values()).sort((a, b) => a.path.localeCompare(b.path));
});

const filteredTreeEntries = computed(() => {
  const query = treeFilter.value.trim().toLowerCase();
  if (!query) {
    return treeEntries.value;
  }
  return treeEntries.value.filter((entry) =>
    entry.path.toLowerCase().includes(query) || entry.name.toLowerCase().includes(query)
  );
});

const filteredTopics = computed(() => {
  if (!selectedBranch.value) {
    return topicsStore.topics;
  }
  const prefix = selectedBranch.value;
  return topicsStore.topics.filter((topic) => {
    const key = topicKey(topic);
    return key ? key.startsWith(prefix) : false;
  });
});

const filteredSubscribers = computed(() => {
  if (!selectedBranch.value) {
    return subscribersStore.subscribers;
  }
  const prefix = selectedBranch.value;
  return subscribersStore.subscribers.filter((subscriber) => {
    if (!subscriber.topic_id) {
      return false;
    }
    const key = topicKeyById.value.get(subscriber.topic_id);
    return key ? key.startsWith(prefix) : false;
  });
});

const pagedTopics = computed(() => {
  const start = (topicsPage.value - 1) * topicsPageSize;
  return filteredTopics.value.slice(start, start + topicsPageSize);
});

const pagedSubscribers = computed(() => {
  const start = (subscribersPage.value - 1) * subscribersPageSize;
  return filteredSubscribers.value.slice(start, start + subscribersPageSize);
});

const topicPageCount = computed(() => Math.max(1, Math.ceil(filteredTopics.value.length / topicsPageSize)));
const subscriberPageCount = computed(() =>
  Math.max(1, Math.ceil(filteredSubscribers.value.length / subscribersPageSize))
);

const resolveTopicLabel = (topicId?: string) => {
  if (!topicId) {
    return "Unknown topic";
  }
  return topicLabelById.value.get(topicId) ?? "Unknown topic";
};

const baseUrl = computed(() => connectionStore.baseUrlDisplay);
const connectionLabel = computed(() => connectionStore.statusLabel);
const wsLabel = computed(() => connectionStore.wsLabel);

const connectionClass = computed(() => {
  if (connectionStore.status === "online") {
    return "cui-status-success";
  }
  if (connectionStore.status === "offline") {
    return "cui-status-danger";
  }
  return "cui-status-accent";
});

const wsClass = computed(() => {
  if (connectionStore.wsLabel.toLowerCase() === "live") {
    return "cui-status-success";
  }
  return "cui-status-accent";
});

const sourceNameById = computed(() => {
  const map = new Map<string, string>();
  usersStore.clients.forEach((client) => {
    if (client.id) {
      map.set(client.id, resolveIdentityLabel(client.display_name, client.id));
    }
  });
  usersStore.identities.forEach((identity) => {
    if (identity.id && !map.has(identity.id)) {
      map.set(identity.id, resolveIdentityLabel(identity.display_name, identity.id));
    }
  });
  return map;
});

const displayNameFromMetadata = (metadata?: Record<string, unknown>) => {
  if (!metadata) {
    return undefined;
  }
  const candidate =
    metadata.display_name ??
    metadata.displayName ??
    metadata.DisplayName ??
    metadata.name ??
    metadata.label ??
    metadata.source ??
    metadata.Source;
  if (typeof candidate !== "string") {
    return undefined;
  }
  const trimmed = candidate.trim();
  return trimmed.length ? trimmed : undefined;
};

const resolveSourceName = (subscriber: Subscriber) => {
  const metadataLabel = displayNameFromMetadata(subscriber.metadata);
  if (metadataLabel) {
    return metadataLabel;
  }
  if (!subscriber.destination) {
    return undefined;
  }
  return sourceNameById.value.get(subscriber.destination) ?? resolveIdentityLabel(undefined, subscriber.destination);
};

const selectBranch = (path: string) => {
  selectedBranch.value = path;
};

const topicOptions = computed(() => {
  const options = topicsStore.topics
    .filter((topic) => topic.id)
    .map((topic) => ({
      value: topic.id as string,
      label: topic.name ? `${topic.name} (${topic.id})` : (topic.id as string)
    }));
  const current = subscriberDraft.value.topic_id;
  if (current && !options.some((option) => option.value === current)) {
    options.unshift({ value: current, label: current });
  }
  return [{ value: "", label: "Select topic" }, ...options];
});

const destinationOptions = computed(() => {
  const identityDisplayNameById = new Map<string, string>();
  usersStore.identities.forEach((identity) => {
    if (identity.id && identity.display_name) {
      identityDisplayNameById.set(identity.id, identity.display_name);
    }
  });
  const options = usersStore.clients
    .filter((client) => client.id)
    .map((client) => ({
      value: client.id as string,
      label: resolveIdentityLabel(
        client.display_name ?? identityDisplayNameById.get(client.id as string),
        client.id
      )
    }));
  const current = subscriberDraft.value.destination;
  if (current && !options.some((option) => option.value === current)) {
    options.unshift({ value: current, label: current });
  }
  return [{ value: "", label: "Select destination" }, ...options];
});

watch(treeEntries, (entries) => {
  if (!entries.length) {
    selectedBranch.value = "";
    return;
  }
  if (!selectedBranch.value || !entries.some((entry) => entry.path === selectedBranch.value)) {
    selectedBranch.value = entries[0].path;
  }
}, { immediate: true });

watch(selectedBranch, () => {
  topicsPage.value = 1;
  subscribersPage.value = 1;
});

watch(topicPageCount, (count) => {
  if (topicsPage.value > count) {
    topicsPage.value = count;
  }
});

watch(subscriberPageCount, (count) => {
  if (subscribersPage.value > count) {
    subscribersPage.value = count;
  }
});

const openTopicModal = (topic: Topic | null) => {
  topicDraft.value = topic ? { ...topic } : { name: "", path: "", description: "" };
  topicModalOpen.value = true;
};

const openSubscriberModal = (subscriber: Subscriber | null) => {
  subscriberDraft.value = subscriber
    ? { ...subscriber }
    : { topic_id: "", destination: "", reject_tests: false };
  subscriberModalOpen.value = true;
};

const saveTopic = async () => {
  try {
    if (topicDraft.value.id) {
      await topicsStore.updateTopic(topicDraft.value);
      toastStore.push("Topic updated", "success");
    } else {
      await topicsStore.createTopic(topicDraft.value);
      toastStore.push("Topic created", "success");
    }
    topicModalOpen.value = false;
  } catch (error) {
    handleApiError(error, "Unable to save topic");
  }
};

const saveSubscriber = async () => {
  const rejectTests = String(subscriberDraft.value.reject_tests).toLowerCase() === "true";
  subscriberDraft.value.reject_tests = rejectTests;
  try {
    if (subscriberDraft.value.id) {
      await subscribersStore.updateSubscriber(subscriberDraft.value);
      toastStore.push("Subscriber updated", "success");
    } else {
      await subscribersStore.addSubscriber(subscriberDraft.value);
      toastStore.push("Subscriber added", "success");
    }
    subscriberModalOpen.value = false;
  } catch (error) {
    handleApiError(error, "Unable to save subscriber");
  }
};

const removeTopic = async (id?: string) => {
  if (!id || !confirm("Delete this topic?")) {
    return;
  }
  try {
    await topicsStore.removeTopic(id);
    toastStore.push("Topic removed", "warning");
  } catch (error) {
    handleApiError(error, "Unable to delete topic");
  }
};

const removeSubscriber = async (id?: string) => {
  if (!id || !confirm("Delete this subscriber?")) {
    return;
  }
  try {
    await subscribersStore.removeSubscriber(id);
    toastStore.push("Subscriber removed", "warning");
  } catch (error) {
    handleApiError(error, "Unable to delete subscriber");
  }
};

const handleApiError = (error: unknown, fallback: string) => {
  const apiError = error as ApiError;
  if (apiError?.status === 401) {
    toastStore.push("Authentication required. Check your credentials.", "warning");
    return;
  }
  if (apiError?.status === 403) {
    toastStore.push("Forbidden. Your account lacks permission for this action.", "warning");
    return;
  }
  toastStore.push(fallback, "danger");
};

onMounted(() => {
  topicsStore.fetchTopics();
  subscribersStore.fetchSubscribers();
  usersStore.fetchUsers();
});
</script>

<style scoped>
.topics-registry {
  --neon: #37f2ff;
  --neon-soft: rgba(55, 242, 255, 0.35);
  --neon-dark: rgba(9, 40, 52, 0.95);
  --panel-dark: rgba(4, 12, 22, 0.96);
  --panel-light: rgba(10, 30, 45, 0.94);
  --amber: #ffb35c;
  --amber-soft: rgba(255, 179, 92, 0.25);
  --danger: rgba(255, 104, 104, 0.8);
  color: #dffcff;
  font-family: "Orbitron", "Rajdhani", "Barlow", sans-serif;
}

.registry-shell {
  position: relative;
  padding: 20px 22px 26px;
  border-radius: 18px;
  border: 1px solid rgba(55, 242, 255, 0.25);
  background: radial-gradient(circle at top, rgba(42, 210, 255, 0.12), transparent 55%),
    linear-gradient(145deg, rgba(5, 16, 28, 0.96), rgba(2, 6, 12, 0.98));
  box-shadow: 0 18px 55px rgba(1, 6, 12, 0.65), inset 0 0 0 1px rgba(55, 242, 255, 0.08);
  overflow: hidden;
}

.registry-shell::before {
  content: "";
  position: absolute;
  inset: 0;
  background: radial-gradient(circle at 1px 1px, rgba(55, 242, 255, 0.08) 1px, transparent 0) 0 0 / 18px 18px;
  opacity: 0.6;
  pointer-events: none;
}

.registry-shell::after {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(120deg, transparent 65%, rgba(55, 242, 255, 0.12), transparent 85%);
  opacity: 0.6;
  pointer-events: none;
}

.registry-top {
  position: relative;
  display: grid;
  grid-template-columns: 1fr auto;
  align-items: center;
  gap: 16px;
  z-index: 1;
}

.registry-title {
  text-align: center;
  justify-self: center;
  font-size: 20px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #d4fbff;
  text-shadow: 0 0 12px rgba(55, 242, 255, 0.5);
}

.registry-status {
  display: flex;
  align-items: center;
  gap: 10px;
  justify-self: end;
}

.status-url {
  font-size: 11px;
  letter-spacing: 0.08em;
  color: rgba(215, 243, 255, 0.8);
}

.registry-grid {
  display: grid;
  grid-template-columns: minmax(240px, 320px) 1fr;
  gap: 18px;
  z-index: 1;
  position: relative;
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
  clip-path: polygon(1px 1px, calc(100% - 25px) 1px, calc(100% - 1px) 25px, calc(100% - 1px) calc(100% - 1px), 25px calc(100% - 1px), 1px calc(100% - 25px));
  pointer-events: none;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 14px;
}

.panel-title {
  font-size: 16px;
  text-transform: uppercase;
  letter-spacing: 0.16em;
  color: #d1fbff;
}

.panel-subtitle {
  font-family: "Rajdhani", "Barlow", sans-serif;
  font-size: 12px;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: rgba(209, 251, 255, 0.65);
  margin-top: 4px;
}

.panel-chip {
  border: 1px solid var(--amber);
  color: var(--amber);
  font-size: 11px;
  padding: 4px 10px;
  border-radius: 999px;
  text-transform: uppercase;
  letter-spacing: 0.18em;
  background: rgba(18, 24, 30, 0.6);
}

.panel-tabs {
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
  color: rgba(209, 251, 255, 0.6);
  padding: 6px 14px;
  border-radius: 999px;
  text-transform: uppercase;
  letter-spacing: 0.18em;
  font-size: 11px;
  transition: all 0.2s ease;
}

.panel-tab.active {
  background: rgba(55, 242, 255, 0.12);
  border-color: rgba(55, 242, 255, 0.6);
  color: #e0feff;
  box-shadow: 0 0 14px rgba(55, 242, 255, 0.25);
}

.tree-search input {
  width: 100%;
  background: rgba(6, 16, 25, 0.85);
  border: 1px solid rgba(55, 242, 255, 0.3);
  color: #d8fbff;
  border-radius: 10px;
  padding: 8px 12px;
  font-size: 12px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.tree-search input::placeholder {
  color: rgba(209, 251, 255, 0.4);
}

.tree-list {
  margin-top: 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 520px;
  overflow: auto;
  padding-right: 6px;
}

.tree-item {
  position: relative;
  display: grid;
  grid-template-columns: 12px 1fr auto;
  align-items: center;
  gap: 8px;
  border: 1px solid transparent;
  background: rgba(7, 18, 28, 0.6);
  color: rgba(213, 251, 255, 0.9);
  padding: 8px 10px;
  padding-left: calc(10px + (var(--depth) * 12px));
  border-radius: 10px;
  text-transform: uppercase;
  letter-spacing: 0.16em;
  font-size: 11px;
  transition: all 0.2s ease;
}

.tree-item:hover {
  border-color: rgba(55, 242, 255, 0.35);
}

.tree-item.active {
  border-color: rgba(55, 242, 255, 0.65);
  background: rgba(55, 242, 255, 0.12);
  box-shadow: 0 0 16px rgba(55, 242, 255, 0.25);
}

.tree-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--neon);
  box-shadow: 0 0 10px var(--neon);
}

.tree-count {
  border: 1px solid var(--amber);
  color: var(--amber);
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 10px;
  letter-spacing: 0.14em;
  background: rgba(10, 20, 30, 0.6);
}

.tree-empty {
  padding: 14px;
  border: 1px dashed rgba(55, 242, 255, 0.3);
  border-radius: 10px;
  text-align: center;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.2em;
  color: rgba(209, 251, 255, 0.6);
}

.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 14px;
}

.registry-card {
  position: relative;
  padding: 16px 16px 12px;
  min-height: 190px;
}

.registry-card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.registry-card-title {
  font-size: 16px;
  color: #e6feff;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.registry-card-subtitle {
  font-size: 11px;
  color: rgba(190, 246, 255, 0.7);
  margin-top: 4px;
}


.registry-card-meta {
  margin-top: 12px;
  display: grid;
  gap: 8px;
  font-family: "Rajdhani", "Barlow", sans-serif;
  font-size: 12px;
  color: rgba(220, 251, 255, 0.85);
}

.registry-card-meta div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  text-transform: uppercase;
  letter-spacing: 0.12em;
}

.registry-card-desc {
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  text-transform: none;
  letter-spacing: 0.02em;
  color: rgba(220, 251, 255, 0.7);
}

.registry-card-actions {
  display: flex;
  gap: 8px;
  margin-top: 14px;
  flex-wrap: wrap;
}

.panel-actions {
  margin-top: 18px;
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  flex-wrap: wrap;
}

.panel-empty {
  grid-column: 1 / -1;
  padding: 18px;
  border: 1px dashed rgba(55, 242, 255, 0.25);
  text-align: center;
  text-transform: uppercase;
  letter-spacing: 0.2em;
  font-size: 12px;
  color: rgba(210, 251, 255, 0.65);
}

.mono {
  font-family: "JetBrains Mono", "Cascadia Mono", monospace;
}

:deep(.topics-registry .cui-btn) {
  background: linear-gradient(135deg, rgba(35, 130, 160, 0.45), rgba(6, 18, 28, 0.92));
  border: 1px solid rgba(55, 242, 255, 0.45);
  color: #e5feff;
  text-transform: uppercase;
  letter-spacing: 0.18em;
  font-size: 10px;
  padding: 6px 12px;
  box-shadow: 0 0 12px rgba(55, 242, 255, 0.15);
}

:deep(.topics-registry .cui-btn--secondary) {
  background: linear-gradient(135deg, rgba(14, 44, 60, 0.85), rgba(6, 14, 22, 0.92));
}

:deep(.topics-registry .cui-btn--danger) {
  border-color: var(--danger);
  color: #ffd3d3;
}

:deep(.topics-registry .cui-btn:disabled) {
  opacity: 0.45;
}

@media (max-width: 1100px) {
  .registry-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .registry-top {
    grid-template-columns: 1fr;
    text-align: center;
  }

  .registry-status {
    justify-content: center;
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
