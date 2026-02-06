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
});
