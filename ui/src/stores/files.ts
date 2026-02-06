import { defineStore } from "pinia";
import { ref } from "vue";
import { endpoints } from "../api/endpoints";
import { del as delRequest, get } from "../api/client";
import type { FileEntry } from "../api/types";

type FileApiPayload = {
  FileID?: number | string;
  Name?: string;
  MediaType?: string;
  Size?: number;
  CreatedAt?: string;
};

const fromApiFile = (payload: FileApiPayload): FileEntry => ({
  id: payload.FileID !== undefined && payload.FileID !== null ? String(payload.FileID) : undefined,
  name: payload.Name,
  content_type: payload.MediaType,
  size: payload.Size,
  created_at: payload.CreatedAt
});

export const useFilesStore = defineStore("files", () => {
  const files = ref<FileEntry[]>([]);
  const images = ref<FileEntry[]>([]);
  const loading = ref(false);

  const fetchFiles = async () => {
    loading.value = true;
    try {
      const fileResponse = await get<FileApiPayload[]>(endpoints.files);
      const imageResponse = await get<FileApiPayload[]>(endpoints.images);
      files.value = fileResponse.map(fromApiFile);
      images.value = imageResponse.map(fromApiFile);
    } finally {
      loading.value = false;
    }
  };

  const fileRawUrl = (id: string) => `${endpoints.files}/${id}/raw`;
  const imageRawUrl = (id: string) => `${endpoints.images}/${id}/raw`;
  const removeFile = async (id: string) => {
    await delRequest(`${endpoints.files}/${id}`);
    files.value = files.value.filter((item) => item.id !== id);
  };
  const removeImage = async (id: string) => {
    await delRequest(`${endpoints.images}/${id}`);
    images.value = images.value.filter((item) => item.id !== id);
  };

  return {
    files,
    images,
    loading,
    fetchFiles,
    fileRawUrl,
    imageRawUrl,
    removeFile,
    removeImage
  };
});
