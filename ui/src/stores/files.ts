import { defineStore } from "pinia";
import { ref } from "vue";
import { endpoints } from "../api/endpoints";
import { get } from "../api/client";
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

  return {
    files,
    images,
    loading,
    fetchFiles,
    fileRawUrl,
    imageRawUrl
  };
});
