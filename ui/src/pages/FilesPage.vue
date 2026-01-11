<template>
  <div class="space-y-6">
    <BaseCard title="Files">
      <div class="mb-4 flex gap-3">
        <BaseButton variant="secondary" @click="filesStore.fetchFiles">Refresh</BaseButton>
      </div>
      <LoadingSkeleton v-if="filesStore.loading" />
      <div v-else class="space-y-3">
        <div v-for="file in filesStore.files" :key="file.id" class="flex flex-wrap items-center justify-between rounded border border-rth-border bg-slate-900 p-3">
          <div>
            <div class="font-semibold">{{ file.name }}</div>
            <div class="text-xs text-slate-400">{{ file.content_type }} · {{ file.size }} bytes</div>
          </div>
          <a class="text-sm text-sky-300 hover:underline" :href="fileUrl(file.id)" target="_blank" rel="noreferrer">Download</a>
        </div>
      </div>
    </BaseCard>

    <BaseCard title="Images">
      <LoadingSkeleton v-if="filesStore.loading" />
      <div v-else class="grid gap-3 md:grid-cols-2">
        <div v-for="image in filesStore.images" :key="image.id" class="rounded border border-rth-border bg-slate-900 p-3">
          <div class="font-semibold">{{ image.name }}</div>
          <div class="text-xs text-slate-400">{{ image.content_type }} · {{ image.size }} bytes</div>
          <div class="mt-3 flex gap-2">
            <BaseButton variant="secondary" @click="openPreview(image)">Preview</BaseButton>
            <a class="text-sm text-sky-300 hover:underline" :href="imageUrl(image.id)" target="_blank" rel="noreferrer">Download</a>
          </div>
        </div>
      </div>
    </BaseCard>

    <BaseModal :open="previewOpen" title="Image Preview" @close="previewOpen = false">
      <div v-if="previewUrl" class="flex flex-col items-center gap-4">
        <img :src="previewUrl" class="max-h-[400px] rounded" alt="Preview" />
        <a class="text-sm text-sky-300 hover:underline" :href="previewUrl" target="_blank" rel="noreferrer">Open raw</a>
      </div>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from "vue";
import { ref } from "vue";
import BaseButton from "../components/BaseButton.vue";
import BaseCard from "../components/BaseCard.vue";
import BaseModal from "../components/BaseModal.vue";
import LoadingSkeleton from "../components/LoadingSkeleton.vue";
import type { FileEntry } from "../api/types";
import { useConnectionStore } from "../stores/connection";
import { useFilesStore } from "../stores/files";

const filesStore = useFilesStore();
const connectionStore = useConnectionStore();
const previewOpen = ref(false);
const previewUrl = ref("");

const fileUrl = (id?: string) => {
  if (!id) {
    return "#";
  }
  return connectionStore.resolveUrl(filesStore.fileRawUrl(id));
};

const imageUrl = (id?: string) => {
  if (!id) {
    return "#";
  }
  return connectionStore.resolveUrl(filesStore.imageRawUrl(id));
};

const openPreview = (image: FileEntry) => {
  if (!image.id) {
    return;
  }
  previewUrl.value = imageUrl(image.id);
  previewOpen.value = true;
};

onMounted(() => {
  filesStore.fetchFiles();
});
</script>
