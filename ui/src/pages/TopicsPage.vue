<template>
  <div class="topics-registry">
    <div class="registry-shell">
      <CosmicTopStatus title="Topic Registry" />

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

          <LoadingSkeleton v-if="activeTab === 'topics' && (topicsStore.loading || filesStore.loading)" />
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
                  <div><span>Files</span><span>{{ associatedFilesForTopic(topic.id).length }}</span></div>
                  <div><span>Images</span><span>{{ associatedImagesForTopic(topic.id).length }}</span></div>
                  <div class="registry-card-desc">
                    <span>Description</span>
                    <span>{{ topic.description || "No description on record." }}</span>
                  </div>
                </div>
                <div class="topic-assets-grid">
                  <section class="topic-assets-block">
                    <div class="topic-assets-heading">
                      <span>Files</span>
                      <span>{{ associatedFilesForTopic(topic.id).length }}</span>
                    </div>
                    <div v-if="associatedFilesForTopic(topic.id).length" class="topic-assets-list">
                      <div
                        v-for="file in associatedFilesForTopic(topic.id)"
                        :key="`topic-file-${topic.id}-${file.id}`"
                        class="topic-assets-row"
                      >
                        <span class="topic-assets-name">{{ assetDisplayName(file, "File") }}</span>
                        <span class="topic-assets-meta mono">{{ file.id || "Pending" }}</span>
                      </div>
                    </div>
                    <div v-else class="topic-assets-empty">No files linked.</div>
                  </section>
                  <section class="topic-assets-block">
                    <div class="topic-assets-heading">
                      <span>Images</span>
                      <span>{{ associatedImagesForTopic(topic.id).length }}</span>
                    </div>
                    <div v-if="associatedImagesForTopic(topic.id).length" class="topic-assets-list">
                      <div
                        v-for="image in associatedImagesForTopic(topic.id)"
                        :key="`topic-image-${topic.id}-${image.id}`"
                        class="topic-assets-row"
                      >
                        <span class="topic-assets-name">{{ assetDisplayName(image, "Image") }}</span>
                        <span class="topic-assets-meta mono">{{ image.id || "Pending" }}</span>
                      </div>
                    </div>
                    <div v-else class="topic-assets-empty">No images linked.</div>
                  </section>
                </div>
                <div class="registry-card-actions">
                  <BaseButton variant="secondary" icon-left="link" @click="openAssetModal(topic)">Manage Assets</BaseButton>
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
              @click="activeTab === 'topics' ? refreshTopicsView() : subscribersStore.fetchSubscribers()"
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

    <BaseModal :open="assetModalOpen" :title="assetModalTitle" size="lg" @close="closeAssetModal">
      <div v-if="selectedAssetTopic" class="topic-assets-modal-grid">
        <section class="topic-assets-modal-panel">
          <div class="topic-assets-modal-title">Associated Files</div>
          <div class="topic-assets-modal-subtitle">Select a linked file to detach it from this topic.</div>
          <BaseSelect v-model="linkedFileSelection" label="File" :options="selectedTopicFileOptions" />
          <div v-if="selectedLinkedFile" class="topic-assets-selection-meta mono">
            {{ selectedLinkedFile.id || "Pending" }} · {{ assetDisplayName(selectedLinkedFile, "File") }}
          </div>
          <div v-else class="topic-assets-empty">No files are linked to this topic.</div>
          <div class="topic-assets-modal-actions">
            <BaseButton
              variant="ghost"
              icon-left="undo"
              :loading="selectedLinkedFile ? isAssetActionPending(selectedLinkedFile, 'file', 'detach') : false"
              :disabled="assetActionInFlight || !selectedLinkedFile"
              @click="detachSelectedAsset('file')"
            >
              Remove File
            </BaseButton>
          </div>
        </section>

        <section class="topic-assets-modal-panel">
          <div class="topic-assets-modal-title">Associated Images</div>
          <div class="topic-assets-modal-subtitle">Select a linked image to detach it from this topic.</div>
          <BaseSelect v-model="linkedImageSelection" label="Image" :options="selectedTopicImageOptions" />
          <div v-if="selectedLinkedImage" class="topic-assets-selection-meta mono">
            {{ selectedLinkedImage.id || "Pending" }} · {{ assetDisplayName(selectedLinkedImage, "Image") }}
          </div>
          <div v-else class="topic-assets-empty">No images are linked to this topic.</div>
          <div class="topic-assets-modal-actions">
            <BaseButton
              variant="ghost"
              icon-left="undo"
              :loading="selectedLinkedImage ? isAssetActionPending(selectedLinkedImage, 'image', 'detach') : false"
              :disabled="assetActionInFlight || !selectedLinkedImage"
              @click="detachSelectedAsset('image')"
            >
              Remove Image
            </BaseButton>
          </div>
        </section>

        <section class="topic-assets-modal-panel">
          <div class="topic-assets-modal-title">Available Files In Asset Library</div>
          <div class="topic-assets-modal-subtitle">Select an unassigned file from the asset library to link it.</div>
          <BaseSelect v-model="availableFileSelection" label="Library File" :options="availableLibraryFileOptions" />
          <div v-if="selectedAvailableFile" class="topic-assets-selection-meta mono">
            {{ selectedAvailableFile.id || "Pending" }} · {{ assetDisplayName(selectedAvailableFile, "File") }}
          </div>
          <div v-else class="topic-assets-empty">No unassigned files are available.</div>
          <div class="topic-assets-modal-actions">
            <BaseButton
              variant="secondary"
              icon-left="link"
              :loading="selectedAvailableFile ? isAssetActionPending(selectedAvailableFile, 'file', 'attach') : false"
              :disabled="assetActionInFlight || !selectedAvailableFile"
              @click="attachSelectedAsset('file')"
            >
              Attach File
            </BaseButton>
          </div>
        </section>

        <section class="topic-assets-modal-panel">
          <div class="topic-assets-modal-title">Available Images In Asset Library</div>
          <div class="topic-assets-modal-subtitle">Select an unassigned image from the asset library to link it.</div>
          <BaseSelect v-model="availableImageSelection" label="Library Image" :options="availableLibraryImageOptions" />
          <div v-if="selectedAvailableImage" class="topic-assets-selection-meta mono">
            {{ selectedAvailableImage.id || "Pending" }} · {{ assetDisplayName(selectedAvailableImage, "Image") }}
          </div>
          <div v-else class="topic-assets-empty">No unassigned images are available.</div>
          <div class="topic-assets-modal-actions">
            <BaseButton
              variant="secondary"
              icon-left="link"
              :loading="selectedAvailableImage ? isAssetActionPending(selectedAvailableImage, 'image', 'attach') : false"
              :disabled="assetActionInFlight || !selectedAvailableImage"
              @click="attachSelectedAsset('image')"
            >
              Attach Image
            </BaseButton>
          </div>
        </section>
      </div>
    </BaseModal>

    <BaseModal :open="subscriberModalOpen" title="Subscriber" @close="subscriberModalOpen = false">
      <div class="space-y-3">
        <BaseSelect v-model="subscriberDraft.topic_id" label="Topic ID" :options="topicOptions" />
        <BaseSelect v-model="subscriberDraft.destination" label="Destination" :options="destinationOptions" />
        <BaseSelect v-model="subscriberRejectTestsDraft" label="Reject Tests" :options="rejectTestsOptions" />
        <BaseButton icon-left="check" variant="success" @click="saveSubscriber">Save Subscriber</BaseButton>
      </div>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, watch } from "vue";
import { ref } from "vue";
import BaseButton from "../components/BaseButton.vue";
import CosmicTopStatus from "../components/cosmic/CosmicTopStatus.vue";
import BaseInput from "../components/BaseInput.vue";
import BaseModal from "../components/BaseModal.vue";
import BaseSelect from "../components/BaseSelect.vue";
import BasePagination from "../components/BasePagination.vue";
import LoadingSkeleton from "../components/LoadingSkeleton.vue";
import type { ApiError } from "../api/client";
import type { FileEntry } from "../api/types";
import type { Subscriber } from "../api/types";
import type { Topic } from "../api/types";
import { useFilesStore } from "../stores/files";
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

type AssetCategory = "file" | "image";

type AssetMutationMode = "attach" | "detach";

type TopicAssetGroup = {
  files: FileEntry[];
  images: FileEntry[];
};

const topicsStore = useTopicsStore();
const filesStore = useFilesStore();
const subscribersStore = useSubscribersStore();
const usersStore = useUsersStore();
const toastStore = useToastStore();

const topicModalOpen = ref(false);
const assetModalOpen = ref(false);
const subscriberModalOpen = ref(false);
const topicDraft = ref<Topic>({ name: "", path: "", description: "" });
const subscriberDraft = ref<Subscriber>({ topic_id: "", destination: "", reject_tests: false });
const subscriberRejectTestsDraft = ref("false");
const assetModalTopicId = ref("");
const assetActionKey = ref<string | null>(null);
const linkedFileSelection = ref("");
const linkedImageSelection = ref("");
const availableFileSelection = ref("");
const availableImageSelection = ref("");
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

const topicAssetsByTopicId = computed(() => {
  const map = new Map<string, TopicAssetGroup>();
  const registerEntry = (entry: FileEntry, category: AssetCategory) => {
    const topicId = normalizeText(entry.topic_id);
    if (!topicId) {
      return;
    }
    const existing = map.get(topicId) ?? { files: [], images: [] };
    if (category === "image") {
      existing.images.push(entry);
    } else {
      existing.files.push(entry);
    }
    map.set(topicId, existing);
  };
  filesStore.files.forEach((entry) => registerEntry(entry, "file"));
  filesStore.images.forEach((entry) => registerEntry(entry, "image"));
  return map;
});

const topicAssetsFor = (topicId?: string): TopicAssetGroup => {
  if (!topicId) {
    return { files: [], images: [] };
  }
  return topicAssetsByTopicId.value.get(topicId) ?? { files: [], images: [] };
};

const associatedFilesForTopic = (topicId?: string) => topicAssetsFor(topicId).files;

const associatedImagesForTopic = (topicId?: string) => topicAssetsFor(topicId).images;

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

const rejectTestsOptions = [
  { value: "false", label: "False" },
  { value: "true", label: "True" }
];

const selectedAssetTopic = computed(() => {
  return topicsStore.topics.find((topic) => topic.id === assetModalTopicId.value) ?? null;
});

const assetModalTitle = computed(() => {
  return selectedAssetTopic.value ? `Topic Assets: ${topicTitle(selectedAssetTopic.value)}` : "Topic Assets";
});

const selectedTopicFiles = computed(() => associatedFilesForTopic(assetModalTopicId.value));
const selectedTopicImages = computed(() => associatedImagesForTopic(assetModalTopicId.value));

const availableLibraryFiles = computed(() => {
  return filesStore.files.filter((entry) => !normalizeText(entry.topic_id));
});

const availableLibraryImages = computed(() => {
  return filesStore.images.filter((entry) => !normalizeText(entry.topic_id));
});

const assetDisplayName = (entry: FileEntry, fallback: string) => {
  return normalizeText(entry.name) ?? `${fallback} ${entry.id ?? "Pending"}`;
};

const assetSelectLabel = (entry: FileEntry, fallback: string) => {
  const id = entry.id ?? "pending";
  return `${assetDisplayName(entry, fallback)} (${id})`;
};

const buildAssetOptions = (entries: FileEntry[], placeholder: string, fallback: string) => {
  return [
    { value: "", label: placeholder },
    ...entries
      .filter((entry) => entry.id)
      .map((entry) => ({
        value: entry.id as string,
        label: assetSelectLabel(entry, fallback)
      }))
  ];
};

const findAssetById = (entries: FileEntry[], entryId: string) => {
  return entries.find((entry) => entry.id === entryId);
};

const selectedTopicFileOptions = computed(() => {
  return buildAssetOptions(selectedTopicFiles.value, "Select linked file", "File");
});

const selectedTopicImageOptions = computed(() => {
  return buildAssetOptions(selectedTopicImages.value, "Select linked image", "Image");
});

const availableLibraryFileOptions = computed(() => {
  return buildAssetOptions(availableLibraryFiles.value, "Select library file", "File");
});

const availableLibraryImageOptions = computed(() => {
  return buildAssetOptions(availableLibraryImages.value, "Select library image", "Image");
});

const selectedLinkedFile = computed(() => findAssetById(selectedTopicFiles.value, linkedFileSelection.value));
const selectedLinkedImage = computed(() => findAssetById(selectedTopicImages.value, linkedImageSelection.value));
const selectedAvailableFile = computed(() => findAssetById(availableLibraryFiles.value, availableFileSelection.value));
const selectedAvailableImage = computed(() => findAssetById(availableLibraryImages.value, availableImageSelection.value));

const buildAssetActionKey = (entry: FileEntry, category: AssetCategory, mode: AssetMutationMode) => {
  return `${mode}:${category}:${entry.id ?? entry.name ?? "unknown"}`;
};

const assetActionInFlight = computed(() => assetActionKey.value !== null);

const isAssetActionPending = (entry: FileEntry, category: AssetCategory, mode: AssetMutationMode) => {
  return assetActionKey.value === buildAssetActionKey(entry, category, mode);
};

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

const openAssetModal = (topic: Topic) => {
  if (!topic.id) {
    return;
  }
  assetModalTopicId.value = topic.id;
  linkedFileSelection.value = "";
  linkedImageSelection.value = "";
  availableFileSelection.value = "";
  availableImageSelection.value = "";
  assetModalOpen.value = true;
};

const closeAssetModal = () => {
  assetModalOpen.value = false;
  assetModalTopicId.value = "";
  assetActionKey.value = null;
  linkedFileSelection.value = "";
  linkedImageSelection.value = "";
  availableFileSelection.value = "";
  availableImageSelection.value = "";
};

const openSubscriberModal = (subscriber: Subscriber | null) => {
  subscriberDraft.value = subscriber
    ? { ...subscriber }
    : { topic_id: "", destination: "", reject_tests: false };
  subscriberRejectTestsDraft.value = subscriberDraft.value.reject_tests ? "true" : "false";
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
  const rejectTests = subscriberRejectTestsDraft.value === "true";
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

const updateAssetTopic = async (entry: FileEntry, category: AssetCategory, topicId?: string) => {
  if (!entry.id) {
    return;
  }
  const mode: AssetMutationMode = topicId ? "attach" : "detach";
  assetActionKey.value = buildAssetActionKey(entry, category, mode);
  try {
    await filesStore.updateAttachmentTopic({
      category,
      id: entry.id,
      topic_id: topicId
    });
    toastStore.push(topicId ? "Asset linked to topic" : "Asset removed from topic", "success");
  } catch (error) {
    handleApiError(error, topicId ? "Unable to link asset to topic" : "Unable to remove asset from topic");
  } finally {
    assetActionKey.value = null;
  }
};

const attachAssetToTopic = async (entry: FileEntry, category: AssetCategory) => {
  const topicId = assetModalTopicId.value;
  if (!topicId) {
    return;
  }
  await updateAssetTopic(entry, category, topicId);
};

const detachAssetFromTopic = async (entry: FileEntry, category: AssetCategory) => {
  await updateAssetTopic(entry, category, undefined);
};

const attachSelectedAsset = async (category: AssetCategory) => {
  const entry = category === "image" ? selectedAvailableImage.value : selectedAvailableFile.value;
  if (!entry) {
    return;
  }
  await attachAssetToTopic(entry, category);
  if (category === "image") {
    availableImageSelection.value = "";
  } else {
    availableFileSelection.value = "";
  }
};

const detachSelectedAsset = async (category: AssetCategory) => {
  const entry = category === "image" ? selectedLinkedImage.value : selectedLinkedFile.value;
  if (!entry) {
    return;
  }
  await detachAssetFromTopic(entry, category);
  if (category === "image") {
    linkedImageSelection.value = "";
  } else {
    linkedFileSelection.value = "";
  }
};

const refreshTopicsView = async () => {
  await Promise.all([topicsStore.fetchTopics(), filesStore.fetchFiles()]);
};

const removeTopic = async (id?: string) => {
  if (!id || !confirm("Delete this topic?")) {
    return;
  }
  try {
    await topicsStore.removeTopic(id);
    await filesStore.fetchFiles();
    if (assetModalTopicId.value === id) {
      closeAssetModal();
    }
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
  refreshTopicsView();
  subscribersStore.fetchSubscribers();
  usersStore.fetchUsers();
});
</script>

<style scoped src="./styles/TopicsPage.css"></style>




