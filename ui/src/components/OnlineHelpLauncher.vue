<template>
  <div class="cui-help-launcher">
    <button
      type="button"
      class="cui-help-trigger"
      :aria-label="`Open online help for ${helpProfile.title}`"
      :title="`Online help: ${helpProfile.title}`"
      @click="openHelp"
    >
      <span aria-hidden="true">?</span>
    </button>

    <BaseModal :open="modalOpen" :title="helpProfile.title" @close="closeHelp">
      <section class="cui-help-modal" aria-live="polite">
        <div class="cui-help-modal__meta">
          <span>ONLINE HELP</span>
          <span>{{ helpProfile.fileName }}</span>
        </div>
        <p v-if="loading" class="cui-help-modal__status">Synchronizing archive stream...</p>
        <p v-else-if="loadError" class="cui-help-modal__status cui-help-modal__status--error">
          {{ loadError }}
        </p>
        <pre v-else class="cui-help-modal__text"
          >{{ typedText }}<span class="cui-help-modal__cursor" aria-hidden="true"></span
        ></pre>
      </section>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { useRouter } from "vue-router";
import BaseModal from "./BaseModal.vue";
import { getHelpProfileForPath, resolveHelpUrl } from "../utils/online-help";

const helpCache = new Map<string, string>();

const route = useRoute();
const router = useRouter();
const modalOpen = ref(false);
const loading = ref(false);
const loadError = ref("");
const sourceText = ref("");
const typedText = ref("");

let typewriterTimer: number | null = null;
let typewriterIndex = 0;
let requestToken = 0;

const helpProfile = computed(() => getHelpProfileForPath(route.path));

const stopTypewriter = () => {
  if (typewriterTimer !== null) {
    window.clearTimeout(typewriterTimer);
    typewriterTimer = null;
  }
};

const resolveCharacterDelay = (character: string) => {
  if (character === "\n") {
    return 130;
  }
  if (/[.!?]/.test(character)) {
    return 80;
  }
  if (/[,:;]/.test(character)) {
    return 45;
  }
  return 16;
};

const runTypewriter = () => {
  stopTypewriter();
  typedText.value = "";
  typewriterIndex = 0;

  const tick = () => {
    if (typewriterIndex >= sourceText.value.length) {
      typewriterTimer = null;
      return;
    }

    const currentChar = sourceText.value[typewriterIndex] ?? "";
    typewriterIndex += 1;
    typedText.value = sourceText.value.slice(0, typewriterIndex);
    typewriterTimer = window.setTimeout(tick, resolveCharacterDelay(currentChar));
  };

  tick();
};

const isHelpQueryEnabled = (value: unknown): boolean => {
  if (Array.isArray(value)) {
    return value.some((entry) => isHelpQueryEnabled(entry));
  }
  if (typeof value === "boolean") {
    return value;
  }
  if (typeof value === "number") {
    return value === 1;
  }
  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase();
    return normalized === "1" || normalized === "true" || normalized === "yes";
  }
  return false;
};

const openHelpFromQueryIfRequested = () => {
  if (isHelpQueryEnabled(route.query.help) && !modalOpen.value) {
    modalOpen.value = true;
  }
};

const clearHelpQuery = async () => {
  if (!isHelpQueryEnabled(route.query.help)) {
    return;
  }
  const nextQuery = { ...route.query };
  delete nextQuery.help;
  try {
    await router.replace({ path: route.path, query: nextQuery, hash: route.hash });
  } catch {
    // Ignore query cleanup failures; closing the modal should still succeed.
  }
};

const loadHelp = async () => {
  const currentToken = ++requestToken;
  const fileName = helpProfile.value.fileName;
  stopTypewriter();
  typedText.value = "";
  loadError.value = "";
  loading.value = true;

  try {
    let helpText = helpCache.get(fileName);
    if (!helpText) {
      const response = await fetch(resolveHelpUrl(fileName), { cache: "no-store" });
      if (!response.ok) {
        throw new Error(`Help file unavailable: ${fileName}`);
      }
      helpText = await response.text();
      helpCache.set(fileName, helpText);
    }
    if (currentToken !== requestToken) {
      return;
    }
    sourceText.value = helpText.trim();
    loading.value = false;
    runTypewriter();
  } catch (error) {
    if (currentToken !== requestToken) {
      return;
    }
    sourceText.value = "";
    loading.value = false;
    loadError.value = error instanceof Error ? error.message : "Unable to load online help.";
  }
};

const openHelp = () => {
  modalOpen.value = true;
};

const closeHelp = () => {
  modalOpen.value = false;
};

watch(modalOpen, (open) => {
  if (open) {
    void loadHelp();
    return;
  }
  stopTypewriter();
  void clearHelpQuery();
});

watch(helpProfile, () => {
  if (modalOpen.value) {
    void loadHelp();
  }
});

watch(
  () => route.query.help,
  () => {
    openHelpFromQueryIfRequested();
  },
  { immediate: true }
);

onBeforeUnmount(() => {
  stopTypewriter();
});
</script>
