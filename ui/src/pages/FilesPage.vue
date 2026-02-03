<template>
  <div class="space-y-6">
    <BaseCard title="Files & Images">
      <div class="mb-4 cui-tab-group">
        <BaseButton variant="tab" icon-left="file" :class="{ 'cui-tab-active': activeTab === 'files' }" @click="activeTab = 'files'">Files</BaseButton>
        <BaseButton variant="tab" icon-left="image" :class="{ 'cui-tab-active': activeTab === 'images' }" @click="activeTab = 'images'">Images</BaseButton>
      </div>
      <LoadingSkeleton v-if="filesStore.loading" />
      <div v-else>
        <div v-if="activeTab === 'files'" class="space-y-3">
          <div v-for="file in pagedFiles" :key="file.id" class="flex flex-wrap items-center justify-between rounded border border-rth-border bg-rth-panel-muted p-3">
            <div>
              <div class="font-semibold">{{ file.name }}</div>
              <div class="text-xs text-rth-muted">{{ file.content_type }} - {{ formatNumber(file.size) }} bytes</div>
            </div>
            <BaseButton variant="secondary" icon-left="download" @click="downloadAttachment(file, 'file')">Download</BaseButton>
          </div>
          <BasePagination v-model:page="filesPage" :page-size="filesPageSize" :total="filesStore.files.length" />
        </div>

        <div v-else class="space-y-3">
          <div class="grid gap-3 md:grid-cols-2">
            <div v-for="image in pagedImages" :key="image.id" class="rounded border border-rth-border bg-rth-panel-muted p-3">
              <div class="font-semibold">{{ image.name }}</div>
              <div class="text-xs text-rth-muted">{{ image.content_type }} - {{ formatNumber(image.size) }} bytes</div>
              <div class="mt-3 flex gap-2">
                <BaseButton variant="secondary" icon-left="eye" @click="openPreview(image)">Preview</BaseButton>
                <BaseButton variant="secondary" icon-left="download" @click="downloadAttachment(image, 'image')">Download</BaseButton>
              </div>
            </div>
          </div>
          <BasePagination v-model:page="imagesPage" :page-size="imagesPageSize" :total="filesStore.images.length" />
        </div>
      </div>
      <div class="mt-4 flex flex-wrap justify-end gap-2">
        <BaseButton variant="secondary" icon-left="refresh" @click="filesStore.fetchFiles">Refresh</BaseButton>
      </div>
    </BaseCard>

    <BaseModal :open="previewOpen" title="Image Preview" @close="closePreview">
      <div v-if="previewLoading" class="text-sm text-rth-muted">Loading preview...</div>
      <div v-else-if="previewUrl" class="flex flex-col items-center gap-4">
        <img :src="previewUrl" class="max-h-[400px] rounded" :alt="previewName || 'Preview'" />
        <div class="flex gap-2">
          <BaseButton variant="secondary" icon-left="download" @click="downloadPreview">Download</BaseButton>
          <a class="text-sm text-rth-accent hover:underline" :href="previewUrl" target="_blank" rel="noreferrer">Open raw</a>
        </div>
      </div>
      <div v-else class="text-sm text-rth-muted">No preview available.</div>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, watch } from "vue";
import { ref } from "vue";
import BaseButton from "../components/BaseButton.vue";
import BaseCard from "../components/BaseCard.vue";
import BaseModal from "../components/BaseModal.vue";
import BasePagination from "../components/BasePagination.vue";
import LoadingSkeleton from "../components/LoadingSkeleton.vue";
import { getBlob } from "../api/client";
import type { FileEntry } from "../api/types";
import { useFilesStore } from "../stores/files";
import { useToastStore } from "../stores/toasts";
import { formatNumber } from "../utils/format";

const filesStore = useFilesStore();
const toastStore = useToastStore();
const activeTab = ref<"files" | "images">("files");
const previewOpen = ref(false);
const previewUrl = ref("");
const previewName = ref("");
const previewLoading = ref(false);
const filesPage = ref(1);
const imagesPage = ref(1);
const filesPageSize = 6;
const imagesPageSize = 4;

const pagedFiles = computed(() => {
  const start = (filesPage.value - 1) * filesPageSize;
  return filesStore.files.slice(start, start + filesPageSize);
});

const pagedImages = computed(() => {
  const start = (imagesPage.value - 1) * imagesPageSize;
  return filesStore.images.slice(start, start + imagesPageSize);
});

const filePageCount = computed(() => Math.max(1, Math.ceil(filesStore.files.length / filesPageSize)));
const imagePageCount = computed(() => Math.max(1, Math.ceil(filesStore.images.length / imagesPageSize)));

const filePath = (id: string) => filesStore.fileRawUrl(id);
const imagePath = (id: string) => filesStore.imageRawUrl(id);

const triggerDownload = (blob: Blob, name?: string) => {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name || "download";
  link.rel = "noreferrer";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
};

const downloadAttachment = async (entry: FileEntry, type: "file" | "image") => {
  if (!entry.id) {
    return;
  }
  try {
    const path = type === "file" ? filePath(entry.id) : imagePath(entry.id);
    const blob = await getBlob(path);
    triggerDownload(blob, entry.name ?? undefined);
    toastStore.push("Download started", "success");
  } catch (error) {
    toastStore.push("Download failed", "danger");
  }
};

const openPreview = async (image: FileEntry) => {
  if (!image.id) {
    return;
  }
  previewOpen.value = true;
  previewLoading.value = true;
  try {
    const blob = await getBlob(imagePath(image.id));
    clearPreviewUrl();
    previewUrl.value = URL.createObjectURL(blob);
    previewName.value = image.name ?? "";
  } catch (error) {
    toastStore.push("Preview failed", "danger");
  } finally {
    previewLoading.value = false;
  }
};

const closePreview = () => {
  previewOpen.value = false;
};

const downloadPreview = async () => {
  if (!previewUrl.value) {
    return;
  }
  try {
    const blob = await fetch(previewUrl.value).then((response) => response.blob());
    triggerDownload(blob, previewName.value || "preview");
  } catch (error) {
    toastStore.push("Download failed", "danger");
  }
};

const clearPreviewUrl = () => {
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value);
  }
  previewUrl.value = "";
  previewName.value = "";
};

watch(previewOpen, (open) => {
  if (!open) {
    clearPreviewUrl();
  }
});

watch(filePageCount, (count) => {
  if (filesPage.value > count) {
    filesPage.value = count;
  }
});

watch(imagePageCount, (count) => {
  if (imagesPage.value > count) {
    imagesPage.value = count;
  }
});

onMounted(() => {
  filesStore.fetchFiles();
});

onBeforeUnmount(() => {
  clearPreviewUrl();
});
</script>
