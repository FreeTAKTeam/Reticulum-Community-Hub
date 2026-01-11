import { defineStore } from "pinia";
import { ref } from "vue";

export interface ToastMessage {
  id: string;
  message: string;
  tone: "success" | "error" | "warning" | "info";
}

export const useToastStore = defineStore("toast", () => {
  const messages = ref<ToastMessage[]>([]);

  const push = (message: string, tone: ToastMessage["tone"] = "info") => {
    const id = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    messages.value = [...messages.value, { id, message, tone }];
    setTimeout(() => {
      messages.value = messages.value.filter((item) => item.id !== id);
    }, 5000);
  };

  return {
    messages,
    push
  };
});
