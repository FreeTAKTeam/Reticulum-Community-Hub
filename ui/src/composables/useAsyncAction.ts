import { ref } from "vue";

export const useAsyncAction = () => {
  const busy = ref(false);
  const error = ref<unknown>(null);

  const run = async <T>(action: () => Promise<T>): Promise<T> => {
    busy.value = true;
    error.value = null;
    try {
      return await action();
    } catch (actionError) {
      error.value = actionError;
      throw actionError;
    } finally {
      busy.value = false;
    }
  };

  return {
    busy,
    error,
    run
  };
};
