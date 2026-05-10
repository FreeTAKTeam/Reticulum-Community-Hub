import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useFilesStore } from "../src/stores/files";

describe("files store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.restoreAllMocks();
  });

  it("removes file and image entries with delete endpoints", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.endsWith("/File/1") && init?.method === "DELETE") {
        return Promise.resolve(
          new Response(JSON.stringify({ FileID: 1 }), {
            status: 200,
            headers: { "Content-Type": "application/json" }
          })
        );
      }
      if (url.endsWith("/Image/2") && init?.method === "DELETE") {
        return Promise.resolve(
          new Response(JSON.stringify({ FileID: 2 }), {
            status: 200,
            headers: { "Content-Type": "application/json" }
          })
        );
      }
      return Promise.resolve(new Response(JSON.stringify({ detail: "not found" }), { status: 404 }));
    });
    globalThis.fetch = fetchMock as typeof fetch;

    const store = useFilesStore();
    store.files = [{ id: "1", name: "note.txt" }];
    store.images = [{ id: "2", name: "photo.jpg" }];

    await store.removeFile("1");
    await store.removeImage("2");

    expect(store.files).toEqual([]);
    expect(store.images).toEqual([]);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/File/1"),
      expect.objectContaining({ method: "DELETE" })
    );
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/Image/2"),
      expect.objectContaining({ method: "DELETE" })
    );
  });

  it("uploads file and image attachments and prepends them to store state", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.endsWith("/Chat/Attachment") && init?.method === "POST") {
        const form = init.body as FormData;
        const category = form.get("category");
        const file = form.get("file");
        const isFileUpload = category === "file";
        const uploaded = file instanceof File ? file : null;
        return Promise.resolve(
          new Response(
            JSON.stringify({
              FileID: isFileUpload ? 11 : 12,
              Name: uploaded?.name ?? "unknown",
              MediaType: uploaded?.type ?? "application/octet-stream",
              Size: uploaded?.size ?? 0,
              Category: category,
              CreatedAt: "2026-03-04T00:00:00Z"
            }),
            {
              status: 200,
              headers: { "Content-Type": "application/json" }
            }
          )
        );
      }
      return Promise.resolve(new Response(JSON.stringify({ detail: "not found" }), { status: 404 }));
    });
    globalThis.fetch = fetchMock as typeof fetch;

    const store = useFilesStore();
    const textFile = new File(["hello"], "report.txt", { type: "text/plain" });
    const imageFile = new File(["img"], "snapshot.png", { type: "image/png" });

    await store.uploadAttachment({ category: "file", file: textFile });
    await store.uploadAttachment({ category: "image", file: imageFile });

    expect(store.files[0]).toMatchObject({
      id: "11",
      name: "report.txt",
      content_type: "text/plain"
    });
    expect(store.images[0]).toMatchObject({
      id: "12",
      name: "snapshot.png",
      content_type: "image/png"
    });
    const uploadCalls = fetchMock.mock.calls.filter(([input, init]) => {
      const url = typeof input === "string" ? input : input.toString();
      return url.endsWith("/Chat/Attachment") && init?.method === "POST";
    });
    expect(uploadCalls).toHaveLength(2);
    expect(uploadCalls[0]?.[1]?.body).toBeInstanceOf(FormData);
    expect(uploadCalls[1]?.[1]?.body).toBeInstanceOf(FormData);
  });
});
