import { onScopeDispose, watch, type Ref } from "vue";
import { useIdentityDirectoryStore } from "../stores/identity-directory";
import { useConnectionStore } from "../stores/connection";
/** Enrich only the IDs this mounted consumer currently displays. */
export const useIdentityEnrichment = (ids: Ref<string[]>) => {
  const directory = useIdentityDirectoryStore();
  const connection = useConnectionStore();
  const scope = directory.register();
  watch([ids, () => connection.requestIdentity], () => { void directory.setVisible(scope, ids.value); }, { immediate: true });
  onScopeDispose(() => directory.unregister(scope));
  return directory;
};
