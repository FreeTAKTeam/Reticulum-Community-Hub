import { defineStore } from "pinia";
import { ref } from "vue";
import { endpoints } from "../api/endpoints";
import { del } from "../api/client";
import { get } from "../api/client";
import { patch } from "../api/client";
import { post } from "../api/client";
import type { Topic } from "../api/types";

type TopicApiPayload = {
  TopicID?: string;
  TopicName?: string;
  TopicPath?: string;
  TopicDescription?: string;
};

const toApiTopic = (topic: Topic): TopicApiPayload => ({
  TopicID: topic.id,
  TopicName: topic.name,
  TopicPath: topic.path,
  TopicDescription: topic.description
});

const fromApiTopic = (payload: TopicApiPayload): Topic => ({
  id: payload.TopicID,
  name: payload.TopicName,
  path: payload.TopicPath,
  description: payload.TopicDescription
});

export const useTopicsStore = defineStore("topics", () => {
  const topics = ref<Topic[]>([]);
  const loading = ref(false);

  const fetchTopics = async () => {
    loading.value = true;
    try {
      const response = await get<TopicApiPayload[]>(endpoints.topics);
      topics.value = response.map(fromApiTopic);
    } finally {
      loading.value = false;
    }
  };

  const createTopic = async (payload: Topic) => {
    const created = await post<TopicApiPayload>(endpoints.topics, toApiTopic(payload));
    topics.value = [...topics.value, fromApiTopic(created)];
  };

  const updateTopic = async (payload: Topic) => {
    if (!payload.id) {
      return;
    }
    const updated = await patch<TopicApiPayload>(endpoints.topics, toApiTopic(payload));
    const mapped = fromApiTopic(updated);
    topics.value = topics.value.map((topic) => (topic.id === payload.id ? mapped : topic));
  };

  const removeTopic = async (id: string) => {
    await del<void>(`${endpoints.topics}?id=${id}`);
    topics.value = topics.value.filter((topic) => topic.id !== id);
  };

  return {
    topics,
    loading,
    fetchTopics,
    createTopic,
    updateTopic,
    removeTopic
  };
});
