import { defineStore } from "pinia";
import { ref } from "vue";
import { endpoints } from "../api/endpoints";
import { del } from "../api/client";
import { get } from "../api/client";
import { patch } from "../api/client";
import { post } from "../api/client";
import type { Subscriber } from "../api/types";

type SubscriberApiPayload = {
  SubscriberID?: string;
  Destination?: string;
  TopicID?: string;
  RejectTests?: number | null;
  Metadata?: Record<string, unknown> | null;
};

const toApiSubscriber = (subscriber: Subscriber): SubscriberApiPayload => ({
  SubscriberID: subscriber.id,
  Destination: subscriber.destination,
  TopicID: subscriber.topic_id,
  RejectTests: subscriber.reject_tests === undefined ? null : subscriber.reject_tests ? 1 : 0,
  Metadata: subscriber.metadata ?? null
});

const fromApiSubscriber = (payload: SubscriberApiPayload): Subscriber => ({
  id: payload.SubscriberID,
  destination: payload.Destination,
  topic_id: payload.TopicID,
  reject_tests: payload.RejectTests ? payload.RejectTests > 0 : false,
  metadata: payload.Metadata ?? undefined
});

export const useSubscribersStore = defineStore("subscribers", () => {
  const subscribers = ref<Subscriber[]>([]);
  const loading = ref(false);

  const fetchSubscribers = async () => {
    loading.value = true;
    try {
      const response = await get<SubscriberApiPayload[]>(endpoints.subscribers);
      subscribers.value = response.map(fromApiSubscriber);
    } finally {
      loading.value = false;
    }
  };

  const addSubscriber = async (payload: Subscriber) => {
    const created = await post<SubscriberApiPayload>(endpoints.subscribersAdd, toApiSubscriber(payload));
    subscribers.value = [...subscribers.value, fromApiSubscriber(created)];
  };

  const updateSubscriber = async (payload: Subscriber) => {
    if (!payload.id) {
      return;
    }
    const updated = await patch<SubscriberApiPayload>(endpoints.subscribers, toApiSubscriber(payload));
    const mapped = fromApiSubscriber(updated);
    subscribers.value = subscribers.value.map((subscriber) => (subscriber.id === payload.id ? mapped : subscriber));
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
