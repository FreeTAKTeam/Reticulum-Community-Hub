import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { computed, createApp, defineComponent, h, nextTick, ref, type App, type Ref } from "vue";
import { createPinia, setActivePinia } from "pinia";
import { getBlob } from "../api/client";
import { useAttachmentPreviews } from "./useAttachmentPreviews";
import { useConnectionStore } from "../stores/connection";

vi.mock("../api/client", () => ({ getBlob: vi.fn() }));
const settle = async () => { for (let i = 0; i < 25; i += 1) { await Promise.resolve(); } await nextTick(); };

describe("attachment preview ownership", () => {
  let app: App | undefined;
  let host: HTMLDivElement;
  beforeEach(() => {
    localStorage.clear();
    setActivePinia(createPinia());
    vi.mocked(getBlob).mockReset();
    vi.stubGlobal("URL", Object.assign(URL, {
      createObjectURL: vi.fn(() => "blob:fixture"), revokeObjectURL: vi.fn()
    }));
    host = document.createElement("div");
    document.body.appendChild(host);
  });
  afterEach(() => { app?.unmount(); app = undefined; host.remove(); vi.unstubAllGlobals(); });
  const mount = (paths: Ref<string[]>) => {
    let previews!: ReturnType<typeof useAttachmentPreviews>;
    app = createApp(defineComponent({ setup() {
      previews = useAttachmentPreviews(computed(() => paths.value));
      return () => h("div");
    } }));
    app.mount(host);
    return previews;
  };

  it("cancels an invalidated request and never overlaps an uncooperative old download", async () => {
    const completions: ((blob: Blob) => void)[] = [];
    vi.mocked(getBlob).mockImplementation(() => new Promise((resolve) => { completions.push(resolve); }));
    const paths = ref(["/Image/old/raw"]);
    const previews = mount(paths);
    const firstSignal = vi.mocked(getBlob).mock.calls[0][1]?.signal;
    paths.value = ["/Image/second/raw"];
    paths.value = ["/Image/latest/raw"];
    expect(firstSignal?.aborted).toBe(true);
    expect(getBlob).toHaveBeenCalledTimes(1);
    completions[0](new Blob(["old"], { type: "image/png" }));
    await settle();
    expect(getBlob).toHaveBeenCalledTimes(2);
    expect(vi.mocked(getBlob).mock.calls[1][0]).toBe("/Image/latest/raw");
    expect(URL.createObjectURL).not.toHaveBeenCalled();
    completions[1](new Blob(["latest"], { type: "image/png" }));
    await settle();
    expect(Object.keys(previews.urls.value)).toEqual(["/Image/latest/raw"]);
  });

  it("does not create a URL after the view unmounts", async () => {
    let finish!: (blob: Blob) => void;
    vi.mocked(getBlob).mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
    mount(ref(["/Image/1/raw"]));
    const signal = vi.mocked(getBlob).mock.calls[0][1]?.signal;
    app?.unmount(); app = undefined;
    expect(signal?.aborted).toBe(true);
    finish(new Blob(["fixture"], { type: "image/png" }));
    await settle();
    expect(URL.createObjectURL).not.toHaveBeenCalled();
  });

  it("bounds cached previews and revokes them when the target changes or the modal closes", async () => {
    vi.mocked(getBlob).mockResolvedValue(new Blob(["fixture"], { type: "image/png" }));
    const paths = ref(Array.from({ length: 12 }, (_, index) => `/Image/${index}/raw`));
    const previews = mount(paths);
    await settle();
    expect(getBlob).toHaveBeenCalledTimes(8);
    expect(Object.keys(previews.urls.value)).toHaveLength(8);
    paths.value = [];
    expect(Object.keys(previews.urls.value)).toHaveLength(0);
    expect(URL.revokeObjectURL).toHaveBeenCalledTimes(8);
    paths.value = ["/Image/12/raw"];
    await settle();
    useConnectionStore().baseUrl = "https://another.example";
    expect(Object.keys(previews.urls.value)).toHaveLength(0);
    expect(URL.revokeObjectURL).toHaveBeenCalledTimes(9);
    await settle();
  });
});
