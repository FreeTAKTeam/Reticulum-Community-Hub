import { defineStore } from "pinia";
import { ref } from "vue";
import { endpoints } from "../api/endpoints";
import { del } from "../api/client";
import { get } from "../api/client";
import { patch } from "../api/client";
import { post } from "../api/client";
import type { Topic } from "../api/types";

export const useTopicsStore = defineStore("topics", () => {
  const topics = ref<Topic[]>([]);
  const loading = ref(false);

  const fetchTopics = async () => {
    loading.value = true;
    try {
      topics.value = await get<Topic[]>(endpoints.topics);
    } finally {
      loading.value = false;
    }
  };

  const createTopic = async (payload: Topic) => {
    const created = await post<Topic>(endpoints.topics, payload);
    topics.value = [...topics.value, created];
  };

  const updateTopic = async (payload: Topic) => {
    if (!payload.id) {
      return;
    }
    const updated = await patch<Topic>(`${endpoints.topics}?id=${payload.id}`, payload);
    topics.value = topics.value.map((topic) => (topic.id === payload.id ? updated : topic));
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
