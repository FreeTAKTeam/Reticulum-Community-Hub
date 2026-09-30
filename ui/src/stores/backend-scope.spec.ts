import { createPinia, setActivePinia } from "pinia";
import { beforeEach, expect, it, vi } from "vitest";
import { computed, createApp } from "vue";
import { useConnectionStore } from "./connection";
import { useFilesStore } from "./files";
import { useChatStore } from "./chat";
import { useAttachmentPreviews } from "../composables/useAttachmentPreviews";

vi.mock("../api/client", () => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), del: vi.fn(), getBlob: vi.fn() }));
import { get, getBlob } from "../api/client";

beforeEach(() => { setActivePinia(createPinia()); vi.resetAllMocks(); localStorage.clear(); });

it("clears old file IDs and chat preview paths before a new hub refresh can fail", async () => {
  const connection = useConnectionStore();
  const files = useFilesStore();
  const chat = useChatStore();
  vi.mocked(get).mockResolvedValueOnce([{ FileID: 1, Name: "hub A file" }]).mockResolvedValueOnce([]);
  await files.fetchFiles();
  chat.upsertMessage({ message_id: "A", attachments: [{ file_id: 1, category: "image" }] });
  vi.mocked(getBlob).mockResolvedValue(new Blob(["image"], { type: "image/png" }));
  vi.stubGlobal("URL", { ...URL, createObjectURL: vi.fn(() => "blob:A"), revokeObjectURL: vi.fn() });
  const host = document.createElement("div"); document.body.appendChild(host);
  const previewView = createApp({ setup() {
    useAttachmentPreviews(computed(() => chat.messages.flatMap(message =>
      (message.attachments ?? []).map(attachment => `/Image/${attachment.file_id}/raw`))));
    return () => null;
  } });
  previewView.mount(host);
  await Promise.resolve();
  const previewsBeforeSwitch = vi.mocked(getBlob).mock.calls.length;
  connection.baseUrl = "https://hub-b.example";
  expect(files.files).toEqual([]);
  expect(files.images).toEqual([]);
  expect(chat.messages).toEqual([]);
  vi.mocked(get).mockRejectedValue(new Error("hub B offline"));
  await expect(files.fetchFiles()).rejects.toThrow("hub B offline");
  await Promise.resolve();
  expect(files.files).toEqual([]);
  expect(vi.mocked(getBlob)).toHaveBeenCalledTimes(previewsBeforeSwitch);
  previewView.unmount(); host.remove();
  vi.unstubAllGlobals();
});

it("does not combine completed hub A files with hub B images during a multi-request refresh", async () => {
  const connection = useConnectionStore();
  const files = useFilesStore();
  vi.mocked(get).mockImplementationOnce(async () => {
    connection.baseUrl = "https://hub-b.example";
    return [{ FileID: 1, Name: "hub A" }];
  }).mockResolvedValueOnce([{ FileID: 1, Name: "hub B" }]);
  await expect(files.fetchFiles()).rejects.toMatchObject({ name: "AbortError" });
  expect(files.files).toEqual([]);
  expect(files.images).toEqual([]);
  expect(get).toHaveBeenCalledTimes(1);
});
