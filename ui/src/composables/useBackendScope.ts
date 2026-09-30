import { toRaw, watch, type Ref } from "vue";
import { useConnectionStore } from "../stores/connection";

/** Backend records belong to one connection, including its credentials. */
export const useBackendScope = (fields: Ref<unknown>[]) => {
  const connection = useConnectionStore();
  const initial = fields.map((field) => structuredClone(toRaw(field.value)));
  watch(() => connection.requestIdentity, () => {
    fields.forEach((field, index) => { field.value = structuredClone(initial[index]); });
  }, { flush: "sync" });
  return () => {
    const identity = connection.requestIdentity;
    return () => {
      if (identity !== connection.requestIdentity) {
        throw new DOMException("Backend connection changed", "AbortError");
      }
    };
  };
};
