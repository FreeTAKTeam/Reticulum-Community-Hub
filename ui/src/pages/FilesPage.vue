<template>
  <div class="files-registry">
    <div class="registry-shell">
      <header class="registry-top">
        <div class="registry-title">File Registry</div>
        <div class="registry-status">
          <span class="cui-status-pill" :class="connectionClass">{{ connectionLabel }}</span>
          <span class="cui-status-pill" :class="wsClass">{{ wsLabel }}</span>
          <span class="status-url">{{ baseUrl }}</span>
        </div>
      </header>

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
import BaseModal from "../components/BaseModal.vue";
import BasePagination from "../components/BasePagination.vue";
import LoadingSkeleton from "../components/LoadingSkeleton.vue";
import { getBlob } from "../api/client";
import type { FileEntry } from "../api/types";
import { useConnectionStore } from "../stores/connection";
import { useFilesStore } from "../stores/files";
import { useToastStore } from "../stores/toasts";
import { formatNumber } from "../utils/format";
import { formatTimestamp } from "../utils/format";

const filesStore = useFilesStore();
const connectionStore = useConnectionStore();
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
const baseUrl = computed(() => connectionStore.baseUrlDisplay);
const connectionLabel = computed(() => connectionStore.statusLabel);
const wsLabel = computed(() => connectionStore.wsLabel);

const connectionClass = computed(() => {
  if (connectionStore.status === "online") {
    return "cui-status-success";
  }
  if (connectionStore.status === "offline") {
    return "cui-status-danger";
  }
  return "cui-status-accent";
});

const wsClass = computed(() => {
  if (connectionStore.wsLabel.toLowerCase() === "live") {
    return "cui-status-success";
  }
  return "cui-status-accent";
});

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

<style scoped>
.files-registry {
  --neon: #37f2ff;
  --neon-soft: rgba(55, 242, 255, 0.35);
  --neon-dark: rgba(9, 40, 52, 0.95);
  --panel-dark: rgba(4, 12, 22, 0.96);
  --panel-light: rgba(10, 30, 45, 0.94);
  --amber: #ffb35c;
  --danger: rgba(255, 104, 104, 0.8);
  color: #dffcff;
  font-family: "Orbitron", "Rajdhani", "Barlow", sans-serif;
}

.registry-shell {
  position: relative;
  padding: 20px 22px 26px;
  border-radius: 18px;
  border: 1px solid rgba(55, 242, 255, 0.25);
  background: radial-gradient(circle at top, rgba(42, 210, 255, 0.12), transparent 55%),
    linear-gradient(145deg, rgba(5, 16, 28, 0.96), rgba(2, 6, 12, 0.98));
  box-shadow: 0 18px 55px rgba(1, 6, 12, 0.65), inset 0 0 0 1px rgba(55, 242, 255, 0.08);
  overflow: hidden;
}

.registry-shell::before {
  content: "";
  position: absolute;
  inset: 0;
  background: radial-gradient(circle at 1px 1px, rgba(55, 242, 255, 0.08) 1px, transparent 0) 0 0 / 18px 18px;
  opacity: 0.6;
  pointer-events: none;
}

.registry-shell::after {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(120deg, transparent 65%, rgba(55, 242, 255, 0.12), transparent 85%);
  opacity: 0.6;
  pointer-events: none;
}

.registry-top {
  position: relative;
  display: grid;
  grid-template-columns: 1fr auto;
  align-items: center;
  gap: 16px;
  z-index: 1;
}

.registry-title {
  text-align: center;
  justify-self: center;
  font-size: 20px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #d4fbff;
  text-shadow: 0 0 12px rgba(55, 242, 255, 0.5);
}

.registry-status {
  display: flex;
  align-items: center;
  gap: 10px;
  justify-self: end;
}

.status-url {
  font-size: 11px;
  letter-spacing: 0.08em;
  color: rgba(215, 243, 255, 0.8);
}

.registry-grid {
  display: grid;
  grid-template-columns: minmax(240px, 300px) 1fr;
  gap: 18px;
  z-index: 1;
  position: relative;
}

.panel {
  position: relative;
  padding: 16px;
  background: linear-gradient(145deg, var(--panel-light), var(--panel-dark));
  border: 1px solid rgba(55, 242, 255, 0.25);
  box-shadow: inset 0 0 0 1px rgba(55, 242, 255, 0.08), 0 12px 30px rgba(1, 6, 12, 0.6);
  clip-path: polygon(0 0, calc(100% - 24px) 0, 100% 24px, 100% 100%, 24px 100%, 0 calc(100% - 24px));
}

.panel::before {
  content: "";
  position: absolute;
  inset: 0;
  border: 1px solid rgba(55, 242, 255, 0.2);
  clip-path: polygon(
    1px 1px,
    calc(100% - 25px) 1px,
    calc(100% - 1px) 25px,
    calc(100% - 1px) calc(100% - 1px),
    25px calc(100% - 1px),
    1px calc(100% - 25px)
  );
  pointer-events: none;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 14px;
}

.panel-title {
  font-size: 16px;
  text-transform: uppercase;
  letter-spacing: 0.16em;
  color: #d1fbff;
}

.panel-subtitle {
  font-family: "Rajdhani", "Barlow", sans-serif;
  font-size: 12px;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: rgba(209, 251, 255, 0.65);
  margin-top: 4px;
}

.panel-chip {
  border: 1px solid var(--amber);
  color: var(--amber);
  font-size: 11px;
  padding: 4px 10px;
  border-radius: 999px;
  text-transform: uppercase;
  letter-spacing: 0.18em;
  background: rgba(18, 24, 30, 0.6);
}

.panel-tabs {
  display: inline-flex;
  background: rgba(7, 18, 26, 0.8);
  border: 1px solid rgba(55, 242, 255, 0.25);
  border-radius: 999px;
  padding: 4px;
  gap: 4px;
}

.panel-tab {
  border: 1px solid transparent;
  background: transparent;
  color: rgba(209, 251, 255, 0.6);
  padding: 6px 14px;
  border-radius: 999px;
  text-transform: uppercase;
  letter-spacing: 0.18em;
  font-size: 11px;
  transition: all 0.2s ease;
}

.panel-tab.active {
  background: rgba(55, 242, 255, 0.12);
  border-color: rgba(55, 242, 255, 0.6);
  color: #e0feff;
  box-shadow: 0 0 14px rgba(55, 242, 255, 0.25);
}

.tree-list {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tree-item {
  position: relative;
  display: grid;
  grid-template-columns: 12px 1fr auto;
  align-items: center;
  gap: 8px;
  border: 1px solid transparent;
  background: rgba(7, 18, 28, 0.6);
  color: rgba(213, 251, 255, 0.9);
  padding: 8px 10px;
  border-radius: 10px;
  text-transform: uppercase;
  letter-spacing: 0.16em;
  font-size: 11px;
  transition: all 0.2s ease;
}

.tree-item:hover {
  border-color: rgba(55, 242, 255, 0.35);
}

.tree-item.active {
  border-color: rgba(55, 242, 255, 0.65);
  background: rgba(55, 242, 255, 0.12);
  box-shadow: 0 0 16px rgba(55, 242, 255, 0.25);
}

.tree-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--neon);
  box-shadow: 0 0 10px var(--neon);
}

.tree-count {
  border: 1px solid var(--amber);
  color: var(--amber);
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 10px;
  letter-spacing: 0.14em;
  background: rgba(10, 20, 30, 0.6);
}

.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(270px, 1fr));
  gap: 14px;
}

.registry-card {
  position: relative;
  padding: 16px 16px 12px;
  min-height: 200px;
}

.registry-card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.registry-card-title {
  font-size: 16px;
  color: #e6feff;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.registry-card-subtitle {
  font-size: 11px;
  color: rgba(190, 246, 255, 0.7);
  margin-top: 4px;
}

.registry-card-tag {
  border: 1px solid rgba(55, 242, 255, 0.45);
  color: rgba(227, 252, 255, 0.85);
  font-size: 10px;
  border-radius: 999px;
  padding: 4px 10px;
  text-transform: uppercase;
  letter-spacing: 0.14em;
}

.registry-card-meta {
  margin-top: 12px;
  display: grid;
  gap: 8px;
  font-family: "Rajdhani", "Barlow", sans-serif;
  font-size: 12px;
  color: rgba(220, 251, 255, 0.85);
}

.registry-card-meta div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  text-transform: uppercase;
  letter-spacing: 0.12em;
}

.registry-card-actions {
  display: flex;
  gap: 8px;
  margin-top: 14px;
  flex-wrap: wrap;
}

.panel-empty {
  grid-column: 1 / -1;
  padding: 18px;
  border: 1px dashed rgba(55, 242, 255, 0.25);
  text-align: center;
  text-transform: uppercase;
  letter-spacing: 0.2em;
  font-size: 12px;
  color: rgba(210, 251, 255, 0.65);
}

.panel-pagination {
  margin-top: 16px;
}

.panel-actions {
  margin-top: 18px;
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  flex-wrap: wrap;
}

.mono {
  font-family: "JetBrains Mono", "Cascadia Mono", monospace;
}

.preview-shell {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
}

.preview-image {
  max-height: 420px;
  border-radius: 10px;
  border: 1px solid rgba(55, 242, 255, 0.3);
}

.preview-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.preview-message {
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgba(209, 251, 255, 0.75);
}

.preview-link {
  font-size: 12px;
  color: rgba(180, 246, 255, 0.92);
  text-decoration: underline;
  text-underline-offset: 2px;
}

:deep(.files-registry .cui-btn) {
  background: linear-gradient(135deg, rgba(35, 130, 160, 0.45), rgba(6, 18, 28, 0.92));
  border: 1px solid rgba(55, 242, 255, 0.45);
  color: #e5feff;
  text-transform: uppercase;
  letter-spacing: 0.18em;
  font-size: 10px;
  padding: 6px 12px;
  box-shadow: 0 0 12px rgba(55, 242, 255, 0.15);
}

:deep(.files-registry .cui-btn--secondary) {
  background: linear-gradient(135deg, rgba(14, 44, 60, 0.85), rgba(6, 14, 22, 0.92));
}

:deep(.files-registry .cui-btn--danger) {
  border-color: var(--danger);
  color: #ffd3d3;
}

:deep(.files-registry .cui-btn:disabled) {
  opacity: 0.45;
}

@media (max-width: 1100px) {
  .registry-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .registry-top {
    grid-template-columns: 1fr;
    text-align: center;
  }

  .registry-status {
    justify-content: center;
  }

  .panel-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .panel-tabs {
    align-self: flex-start;
  }
}
</style>
