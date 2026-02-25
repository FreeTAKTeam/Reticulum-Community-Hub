<template>
  <div class="files-registry">
    <div class="registry-shell">
      <CosmicTopStatus title="File Registry" />

      <div class="registry-grid">
        <aside class="panel registry-tree">
          <div class="panel-header">
            <div>
              <div class="panel-title">Asset Library</div>
              <div class="panel-subtitle">Browse Type</div>
            </div>
            <div class="panel-chip">{{ totalEntries }} items</div>
          </div>

          <div class="tree-list">
            <button class="tree-item" :class="{ active: activeTab === 'files' }" type="button" @click="activeTab = 'files'">
              <span class="tree-dot" aria-hidden="true"></span>
              <span class="tree-label">Files</span>
              <span class="tree-count">{{ filesStore.files.length }}</span>
            </button>
            <button class="tree-item" :class="{ active: activeTab === 'images' }" type="button" @click="activeTab = 'images'">
              <span class="tree-dot" aria-hidden="true"></span>
              <span class="tree-label">Images</span>
              <span class="tree-count">{{ filesStore.images.length }}</span>
            </button>
          </div>
        </aside>

        <section class="panel registry-main">
          <div class="panel-header">
            <div>
              <div class="panel-title">{{ activeTabTitle }}</div>
              <div class="panel-subtitle">Metadata and Actions</div>
            </div>
            <div class="panel-tabs">
              <button class="panel-tab" :class="{ active: activeTab === 'files' }" type="button" @click="activeTab = 'files'">
                Files
              </button>
              <button class="panel-tab" :class="{ active: activeTab === 'images' }" type="button" @click="activeTab = 'images'">
                Images
              </button>
            </div>
          </div>

          <LoadingSkeleton v-if="filesStore.loading" />
          <div v-else>
            <div v-if="activeTab === 'files'" class="card-grid">
              <div
                v-for="(file, index) in pagedFiles"
                :key="`file-${file.id ?? file.name ?? index}`"
                class="registry-card cui-panel"
              >
                <div class="registry-card-header">
                  <div>
                    <div class="registry-card-title">{{ file.name || "Unnamed File" }}</div>
                    <div class="registry-card-subtitle mono">{{ file.id || "Pending ID" }}</div>
                  </div>
                  <div class="registry-card-tag">File</div>
                </div>
                <div class="registry-card-meta">
                  <div><span>Media Type</span><span class="mono">{{ file.content_type || "unknown" }}</span></div>
                  <div><span>Size</span><span>{{ formatNumber(file.size ?? 0) }} bytes</span></div>
                  <div><span>Created</span><span>{{ formatTimestamp(file.created_at) }}</span></div>
                </div>
                <div class="registry-card-actions">
                  <BaseButton variant="secondary" icon-left="download" @click="downloadAttachment(file, 'file')">Download</BaseButton>
                  <BaseButton variant="danger" icon-left="trash" @click="removeAttachment(file, 'file')">Delete</BaseButton>
                </div>
              </div>
              <div v-if="pagedFiles.length === 0" class="panel-empty">No files available.</div>
            </div>

            <div v-else class="card-grid">
              <div
                v-for="(image, index) in pagedImages"
                :key="`image-${image.id ?? image.name ?? index}`"
                class="registry-card cui-panel"
              >
                <div class="registry-card-header">
                  <div>
                    <div class="registry-card-title">{{ image.name || "Unnamed Image" }}</div>
                    <div class="registry-card-subtitle mono">{{ image.id || "Pending ID" }}</div>
                  </div>
                  <div class="registry-card-tag">Image</div>
                </div>
                <div class="registry-card-meta">
                  <div><span>Media Type</span><span class="mono">{{ image.content_type || "unknown" }}</span></div>
                  <div><span>Size</span><span>{{ formatNumber(image.size ?? 0) }} bytes</span></div>
                  <div><span>Created</span><span>{{ formatTimestamp(image.created_at) }}</span></div>
                </div>
                <div class="registry-card-actions">
                  <BaseButton variant="secondary" icon-left="eye" @click="openPreview(image)">Preview</BaseButton>
                  <BaseButton variant="secondary" icon-left="download" @click="downloadAttachment(image, 'image')">Download</BaseButton>
                  <BaseButton variant="danger" icon-left="trash" @click="removeAttachment(image, 'image')">Delete</BaseButton>
                </div>
              </div>
              <div v-if="pagedImages.length === 0" class="panel-empty">No images available.</div>
            </div>

            <BasePagination
              v-if="activeTab === 'files' && filesStore.files.length"
              v-model:page="filesPage"
              class="panel-pagination"
              :page-size="filesPageSize"
              :total="filesStore.files.length"
            />
            <BasePagination
              v-else-if="activeTab === 'images' && filesStore.images.length"
              v-model:page="imagesPage"
              class="panel-pagination"
              :page-size="imagesPageSize"
              :total="filesStore.images.length"
            />
          </div>

          <div class="panel-actions">
            <BaseButton variant="secondary" icon-left="refresh" @click="filesStore.fetchFiles()">Refresh</BaseButton>
          </div>
        </section>
      </div>
    </div>

    <BaseModal :open="previewOpen" title="Image Preview" @close="closePreview">
      <div v-if="previewLoading" class="preview-message">Loading preview...</div>
      <div v-else-if="previewUrl" class="preview-shell">
        <img :src="previewUrl" class="preview-image" :alt="previewName || 'Preview'" />
        <div class="preview-actions">
          <BaseButton variant="secondary" icon-left="download" @click="downloadPreview">Download</BaseButton>
          <a class="preview-link" :href="previewUrl" target="_blank" rel="noreferrer">Open raw</a>
        </div>
      </div>
      <div v-else class="preview-message">No preview available.</div>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, watch } from "vue";
import { ref } from "vue";
import BaseButton from "../components/BaseButton.vue";
import CosmicTopStatus from "../components/cosmic/CosmicTopStatus.vue";
import BaseModal from "../components/BaseModal.vue";
import BasePagination from "../components/BasePagination.vue";
import LoadingSkeleton from "../components/LoadingSkeleton.vue";
import { getBlob } from "../api/client";
import type { FileEntry } from "../api/types";
import { useFilesStore } from "../stores/files";
import { useToastStore } from "../stores/toasts";
import { formatNumber } from "../utils/format";
import { formatTimestamp } from "../utils/format";

const filesStore = useFilesStore();
const toastStore = useToastStore();
const activeTab = ref<"files" | "images">("files");
const previewOpen = ref(false);
const previewUrl = ref("");
const previewName = ref("");
const previewLoading = ref(false);
const filesPage = ref(1);
const imagesPage = ref(1);
const filesPageSize = 8;
const imagesPageSize = 8;

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
const totalEntries = computed(() => filesStore.files.length + filesStore.images.length);
const activeTabTitle = computed(() => (activeTab.value === "files" ? "Files" : "Images"));

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

const removeAttachment = async (entry: FileEntry, type: "file" | "image") => {
  if (!entry.id) {
    return;
  }
  const label = entry.name ?? `${type} attachment`;
  const confirmed = window.confirm(`Delete ${label}? This removes it from the database and disk.`);
  if (!confirmed) {
    return;
  }
  try {
    if (type === "file") {
      await filesStore.removeFile(entry.id);
    } else {
      await filesStore.removeImage(entry.id);
      if (previewOpen.value && previewName.value === entry.name) {
        closePreview();
      }
    }
    toastStore.push("Attachment deleted", "success");
  } catch (error) {
    toastStore.push("Delete failed", "danger");
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

watch(activeTab, (tab) => {
  if (tab === "files") {
    filesPage.value = 1;
    return;
  }
  imagesPage.value = 1;
});

onMounted(() => {
  filesStore.fetchFiles();
});

onBeforeUnmount(() => {
  clearPreviewUrl();
});
</script>

<style scoped src="./styles/FilesPage.css"></style>




