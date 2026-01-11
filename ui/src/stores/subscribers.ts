import { defineStore } from "pinia";
import { ref } from "vue";
import { endpoints } from "../api/endpoints";
import { del } from "../api/client";
import { get } from "../api/client";
import { patch } from "../api/client";
import { post } from "../api/client";
import type { Subscriber } from "../api/types";

export const useSubscribersStore = defineStore("subscribers", () => {
  const subscribers = ref<Subscriber[]>([]);
  const loading = ref(false);

  const fetchSubscribers = async () => {
    loading.value = true;
    try {
      subscribers.value = await get<Subscriber[]>(endpoints.subscribers);
    } finally {
      loading.value = false;
    }
  };

  const addSubscriber = async (payload: Subscriber) => {
    const created = await post<Subscriber>(endpoints.subscribersAdd, payload);
    subscribers.value = [...subscribers.value, created];
  };

  const updateSubscriber = async (payload: Subscriber) => {
    if (!payload.id) {
      return;
    }
    const updated = await patch<Subscriber>(`${endpoints.subscribers}?id=${payload.id}`, payload);
    subscribers.value = subscribers.value.map((subscriber) =>
      subscriber.id === payload.id ? updated : subscriber
    );
  };

  const removeSubscriber = async (id: string) => {
    await del<void>(`${endpoints.subscribers}?id=${id}`);
    subscribers.value = subscribers.value.filter((subscriber) => subscriber.id !== id);
  };

  return {
    subscribers,
    loading,
    fetchSubscribers,
    addSubscriber,
    updateSubscriber,
    removeSubscriber
  };
});
