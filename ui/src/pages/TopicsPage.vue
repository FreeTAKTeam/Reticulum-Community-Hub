<template>
  <div class="space-y-6">
    <BaseCard title="Topics">
      <div class="mb-4 flex flex-wrap gap-3">
        <BaseButton @click="openTopicModal(null)">New Topic</BaseButton>
        <BaseButton variant="secondary" @click="topicsStore.fetchTopics">Refresh</BaseButton>
      </div>
      <LoadingSkeleton v-if="topicsStore.loading" />
      <div v-else class="space-y-3">
        <div v-for="topic in topicsStore.topics" :key="topic.id" class="flex flex-wrap items-center justify-between rounded border border-rth-border bg-slate-900 p-3">
          <div>
            <div class="font-semibold">{{ topic.name }}</div>
            <div class="text-xs text-slate-400">{{ topic.path }}</div>
          </div>
          <div class="flex gap-2">
            <BaseButton variant="secondary" @click="openTopicModal(topic)">Edit</BaseButton>
            <BaseButton variant="ghost" @click="removeTopic(topic.id)">Delete</BaseButton>
          </div>
        </div>
      </div>
    </BaseCard>

    <BaseCard title="Subscribers">
      <div class="mb-4 flex flex-wrap gap-3">
        <BaseButton @click="openSubscriberModal(null)">Add Subscriber</BaseButton>
        <BaseButton variant="secondary" @click="subscribersStore.fetchSubscribers">Refresh</BaseButton>
      </div>
      <LoadingSkeleton v-if="subscribersStore.loading" />
      <div v-else class="space-y-3">
        <div v-for="subscriber in subscribersStore.subscribers" :key="subscriber.id" class="flex flex-wrap items-center justify-between rounded border border-rth-border bg-slate-900 p-3">
          <div>
            <div class="font-semibold">{{ subscriber.destination }}</div>
            <div class="text-xs text-slate-400">Topic: {{ subscriber.topic_id }}</div>
          </div>
          <div class="flex gap-2">
            <BaseButton variant="secondary" @click="openSubscriberModal(subscriber)">Edit</BaseButton>
            <BaseButton variant="ghost" @click="removeSubscriber(subscriber.id)">Delete</BaseButton>
          </div>
        </div>
      </div>
    </BaseCard>

    <BaseModal :open="topicModalOpen" title="Topic" @close="topicModalOpen = false">
      <div class="space-y-3">
        <BaseInput v-model="topicDraft.name" label="Name" />
        <BaseInput v-model="topicDraft.path" label="Path" />
        <BaseInput v-model="topicDraft.description" label="Description" />
        <BaseButton @click="saveTopic">Save Topic</BaseButton>
      </div>
    </BaseModal>

    <BaseModal :open="subscriberModalOpen" title="Subscriber" @close="subscriberModalOpen = false">
      <div class="space-y-3">
        <BaseInput v-model="subscriberDraft.topic_id" label="Topic ID" />
        <BaseInput v-model="subscriberDraft.destination" label="Destination" />
        <BaseInput v-model="subscriberDraft.reject_tests" label="Reject Tests (true/false)" />
        <BaseButton @click="saveSubscriber">Save Subscriber</BaseButton>
      </div>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from "vue";
import { ref } from "vue";
import BaseButton from "../components/BaseButton.vue";
import BaseCard from "../components/BaseCard.vue";
import BaseInput from "../components/BaseInput.vue";
import BaseModal from "../components/BaseModal.vue";
import LoadingSkeleton from "../components/LoadingSkeleton.vue";
import type { Subscriber } from "../api/types";
import type { Topic } from "../api/types";
import { useSubscribersStore } from "../stores/subscribers";
import { useTopicsStore } from "../stores/topics";
import { useToastStore } from "../stores/toasts";

const topicsStore = useTopicsStore();
const subscribersStore = useSubscribersStore();
const toastStore = useToastStore();

const topicModalOpen = ref(false);
const subscriberModalOpen = ref(false);
const topicDraft = ref<Topic>({ name: "", path: "", description: "" });
const subscriberDraft = ref<Subscriber>({ topic_id: "", destination: "", reject_tests: false });

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
  } finally {
    topicModalOpen.value = false;
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
  } finally {
    subscriberModalOpen.value = false;
  }
};

const removeTopic = async (id?: string) => {
  if (!id || !confirm("Delete this topic?")) {
    return;
  }
  await topicsStore.removeTopic(id);
  toastStore.push("Topic removed", "warning");
};

const removeSubscriber = async (id?: string) => {
  if (!id || !confirm("Delete this subscriber?")) {
    return;
  }
  await subscribersStore.removeSubscriber(id);
  toastStore.push("Subscriber removed", "warning");
};

onMounted(() => {
  topicsStore.fetchTopics();
  subscribersStore.fetchSubscribers();
});
</script>
