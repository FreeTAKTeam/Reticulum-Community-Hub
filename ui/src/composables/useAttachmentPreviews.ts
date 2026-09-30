import { onBeforeUnmount, ref, watch, type ComputedRef } from "vue";
import { getBlob } from "../api/client";
import { useConnectionStore } from "../stores/connection";

export const isRasterPreview = (blob: Blob): boolean =>
  ["image/png", "image/jpeg", "image/gif", "image/bmp", "image/webp"].includes(blob.type);

/** One download owner per view; retain at most eight recent raster URLs. */
export const useAttachmentPreviews = (paths: ComputedRef<string[]>) => {
  const connection = useConnectionStore();
  const urls = ref<Record<string, string>>({});
  const loading = ref(false);
  const error = ref("");
  let generation = 0;
  let disposed = false;
  let cachedIdentity = "";
  let running = false;
  let active: AbortController | undefined;
  let recent: string[] = [];
  const clear = () => {
    Object.values(urls.value).forEach((url) => URL.revokeObjectURL(url));
    urls.value = {};
  };
  const drain = async () => {
    if (running || disposed) { return; }
    running = true;
    try {
      let completedGeneration = -1;
      while (!disposed && completedGeneration !== generation) {
        const current = generation;
        const identity = cachedIdentity;
        for (const path of recent) {
          if (disposed || current !== generation) { break; }
          if (urls.value[path]) { continue; }
          const controller = new AbortController();
          active = controller;
          loading.value = true;
          try {
            const blob = await getBlob(path, { signal: controller.signal, retries: 0 });
            if (disposed || current !== generation || identity !== connection.requestIdentity) { break; }
            if (!isRasterPreview(blob)) { throw new Error("Download this file to view its contents."); }
            urls.value[path] = URL.createObjectURL(blob);
          } catch (failure) {
            if (!controller.signal.aborted && !disposed && current === generation) {
              error.value = failure instanceof Error ? failure.message : "Unable to load attachment preview";
              console.warn("Unable to load attachment preview", failure);
            }
          } finally {
            if (active === controller) { active = undefined; }
          }
        }
        completedGeneration = current;
      }
    } finally {
      running = false;
      loading.value = false;
    }
  };
  watch(() => JSON.stringify([connection.requestIdentity, paths.value]), () => {
    generation += 1;
    active?.abort();
    error.value = "";
    if (cachedIdentity !== connection.requestIdentity) { clear(); cachedIdentity = connection.requestIdentity; }
    recent = [...new Set(paths.value)].slice(-8);
    for (const path of Object.keys(urls.value)) {
      if (!recent.includes(path)) { URL.revokeObjectURL(urls.value[path]); delete urls.value[path]; }
    }
    void drain();
  }, { immediate: true, flush: "sync" });
  onBeforeUnmount(() => { disposed = true; generation += 1; active?.abort(); clear(); });
  return { urls, loading, error };
};
