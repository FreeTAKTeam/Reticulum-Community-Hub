<template>
  <div class="space-y-6">
    <BaseCard title="Topics & Subscribers">
      <div class="mb-4 flex flex-wrap gap-2">
        <BaseButton variant="tab" icon-left="layers" :class="{ 'cui-tab-active': activeTab === 'topics' }" @click="activeTab = 'topics'">
          Topics
        </BaseButton>
        <BaseButton variant="tab" icon-left="users" :class="{ 'cui-tab-active': activeTab === 'subscribers' }" @click="activeTab = 'subscribers'">
          Subscribers
        </BaseButton>
      </div>
      <LoadingSkeleton v-if="activeTab === 'topics' && topicsStore.loading" />
      <LoadingSkeleton v-else-if="activeTab === 'subscribers' && subscribersStore.loading" />
      <div v-else>
        <div v-if="activeTab === 'topics'" class="space-y-3">
          <div v-for="topic in pagedTopics" :key="topic.id" class="flex flex-wrap items-center justify-between rounded border border-rth-border bg-rth-panel-muted p-3">
            <div>
              <div class="font-semibold">{{ topic.name }}</div>
              <div class="text-xs text-rth-muted">{{ topic.path }}</div>
            </div>
            <div class="flex gap-2">
              <BaseButton variant="secondary" icon-left="edit" @click="openTopicModal(topic)">Edit</BaseButton>
              <BaseButton variant="danger" icon-left="trash" @click="removeTopic(topic.id)">Delete</BaseButton>
            </div>
          </div>
          <BasePagination v-model:page="topicsPage" :page-size="topicsPageSize" :total="topicsStore.topics.length" />
        </div>
        <div v-else class="space-y-3">
          <div v-for="subscriber in pagedSubscribers" :key="subscriber.id" class="flex flex-wrap items-center justify-between rounded border border-rth-border bg-rth-panel-muted p-3">
            <div>
              <div class="font-semibold">{{ resolveSourceName(subscriber) || "Unknown source" }}</div>
              <div class="text-xs text-rth-muted">Topic: {{ resolveTopicName(subscriber.topic_id) }}</div>
            </div>
            <div class="flex gap-2">
              <BaseButton variant="secondary" icon-left="edit" @click="openSubscriberModal(subscriber)">Edit</BaseButton>
              <BaseButton variant="danger" icon-left="trash" @click="removeSubscriber(subscriber.id)">Delete</BaseButton>
            </div>
          </div>
          <BasePagination v-model:page="subscribersPage" :page-size="subscribersPageSize" :total="subscribersStore.subscribers.length" />
        </div>
      </div>
      <div class="mt-4 flex flex-wrap justify-end gap-2">
        <BaseButton v-if="activeTab === 'topics'" icon-left="plus" @click="openTopicModal(null)">New Topic</BaseButton>
        <BaseButton v-if="activeTab === 'subscribers'" icon-left="plus" @click="openSubscriberModal(null)">Add Subscriber</BaseButton>
        <BaseButton variant="secondary" icon-left="refresh" @click="activeTab === 'topics' ? topicsStore.fetchTopics() : subscribersStore.fetchSubscribers()">
          Refresh
        </BaseButton>
      </div>
    </BaseCard>

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
import BaseCard from "../components/BaseCard.vue";
import BaseInput from "../components/BaseInput.vue";
import BaseModal from "../components/BaseModal.vue";
import BaseSelect from "../components/BaseSelect.vue";
import BasePagination from "../components/BasePagination.vue";
import LoadingSkeleton from "../components/LoadingSkeleton.vue";
import type { ApiError } from "../api/client";
import type { Subscriber } from "../api/types";
import type { Topic } from "../api/types";
import { useSubscribersStore } from "../stores/subscribers";
import { useTopicsStore } from "../stores/topics";
import { useToastStore } from "../stores/toasts";
import { useUsersStore } from "../stores/users";
import { resolveIdentityLabel } from "../utils/identity";

const topicsStore = useTopicsStore();
const subscribersStore = useSubscribersStore();
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

const pagedTopics = computed(() => {
  const start = (topicsPage.value - 1) * topicsPageSize;
  return topicsStore.topics.slice(start, start + topicsPageSize);
});

const pagedSubscribers = computed(() => {
  const start = (subscribersPage.value - 1) * subscribersPageSize;
  return subscribersStore.subscribers.slice(start, start + subscribersPageSize);
});

const topicPageCount = computed(() => Math.max(1, Math.ceil(topicsStore.topics.length / topicsPageSize)));
const subscriberPageCount = computed(() =>
  Math.max(1, Math.ceil(subscribersStore.subscribers.length / subscribersPageSize))
);

const topicNameById = computed(() => {
  const map = new Map<string, string>();
  topicsStore.topics.forEach((topic) => {
    if (topic.id && topic.name) {
      map.set(topic.id, topic.name);
    }
  });
  return map;
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

const resolveTopicName = (topicId?: string) => {
  if (!topicId) {
    return "Unknown topic";
  }
  return topicNameById.value.get(topicId) ?? "Unknown topic";
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
