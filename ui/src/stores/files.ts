import { defineStore } from "pinia";
import { ref } from "vue";
import { endpoints } from "../api/endpoints";
import { get } from "../api/client";
import type { FileEntry } from "../api/types";

export const useFilesStore = defineStore("files", () => {
  const files = ref<FileEntry[]>([]);
  const images = ref<FileEntry[]>([]);
  const loading = ref(false);

  const fetchFiles = async () => {
    loading.value = true;
    try {
      files.value = await get<FileEntry[]>(endpoints.files);
      images.value = await get<FileEntry[]>(endpoints.images);
    } finally {
      loading.value = false;
    }
  };

  const fileRawUrl = (id: string) => `${endpoints.files}/${id}/raw`;
  const imageRawUrl = (id: string) => `${endpoints.images}/${id}/raw`;

  return {
    files,
    images,
    loading,
    fetchFiles,
    fileRawUrl,
    imageRawUrl
  };
});
