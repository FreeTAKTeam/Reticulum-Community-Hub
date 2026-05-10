import { ref } from "vue";
import { defineStore } from "pinia";
import { loadJson } from "../utils/storage";
import { saveJson } from "../utils/storage";

interface NavPreferences {
  collapsed: boolean;
  pinned: boolean;
}

const STORAGE_KEY = "rth-ui-nav";

export const useNavStore = defineStore("nav", () => {
  const stored = loadJson<NavPreferences>(STORAGE_KEY, {
    collapsed: false,
    pinned: true
  });

  const isCollapsed = ref<boolean>(stored.collapsed ?? false);
  const isPinned = ref<boolean>(stored.pinned ?? true);

  if (isPinned.value && isCollapsed.value) {
    isCollapsed.value = false;
  }

  const persist = () => {
    saveJson(STORAGE_KEY, {
      collapsed: isCollapsed.value,
      pinned: isPinned.value
    });
  };

  const setCollapsed = (value: boolean) => {
    isCollapsed.value = value;
    if (value) {
      isPinned.value = false;
    }
    persist();
  };

  const setPinned = (value: boolean) => {
    isPinned.value = value;
    if (value) {
      isCollapsed.value = false;
    }
    persist();
  };

  const toggleCollapsed = () => {
    setCollapsed(!isCollapsed.value);
  };

  const togglePinned = () => {
    setPinned(!isPinned.value);
  };

  const collapseIfUnpinned = () => {
    if (!isPinned.value) {
      setCollapsed(true);
    }
  };

  return {
    isCollapsed,
    isPinned,
    setCollapsed,
    setPinned,
    toggleCollapsed,
    togglePinned,
    collapseIfUnpinned
  };
});
