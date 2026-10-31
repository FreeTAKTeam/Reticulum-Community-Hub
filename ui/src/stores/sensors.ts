import { defineStore } from "pinia";
import { ref, shallowRef } from "vue";
import { useBackendScope } from "../composables/useBackendScope";
import { sensorOrigins, type SensorOrigin } from "../api/sensors";
export const useSensorsStore = defineStore("sensors", () => {
  const origins = shallowRef<SensorOrigin[]>([]);
  const observedAtMs = ref(0);
  const error = ref("");
  const scope = useBackendScope([origins, observedAtMs, error]);
  const hidden = ref<string[]>([]);
  let loading = false;
  async function refresh() {
    if (loading) return;
    const current = scope();
    loading = true;
    try { const result = await sensorOrigins(); current(); origins.value = result.items; observedAtMs.value = result.observedAtMs; error.value = ""; }
    catch (cause) {
      if ((cause as Error).name !== "AbortError") {
        origins.value = [];
        error.value = cause instanceof Error ? cause.message : String(cause);
      }
    }
    finally { loading = false; }
  }
  function visible(key: string) { return !hidden.value.includes(key); }
  function toggle(key: string) { hidden.value = visible(key) ? [...hidden.value, key] : hidden.value.filter((id) => id !== key); }
  return {origins, observedAtMs, error, refresh, visible, toggle};
});
