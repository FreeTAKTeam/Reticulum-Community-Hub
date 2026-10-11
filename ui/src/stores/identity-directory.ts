import { defineStore } from "pinia";
import { ref, watch } from "vue";
import { useConnectionStore } from "./connection";
import { loadIdentitySettings, loadIdentityPage, normalizeIdentity, UnsupportedIdentityDirectory, type IdentityDirectorySettings, type IdentityQuery } from "../api/identity-directory";
import type { IdentityEntry } from "../api/types";

const message = (error: unknown) => error instanceof Error ? error.message : "Unable to load identities.";
export const useIdentityDirectoryStore = defineStore("identity-directory", () => {
  const connection = useConnectionStore();
  const revision = ref(0);
  const settings = ref<IdentityDirectorySettings | null>(null);
  const items = ref<IdentityEntry[]>([]);
  const total = ref<number | null>(null);
  const loading = ref(false);
  const error = ref<string | null>(null);
  const unsupported = ref(false);
  const cache = ref(new Map<string, IdentityEntry | null>());
  const lookupErrors = ref(new Map<string, string>());
  let epoch = 0;
  let pageGeneration = 0;
  let pageOwner: AbortController | undefined;
  let settingsOwner: AbortController | undefined;
  let settingsPending: Promise<IdentityDirectorySettings> | undefined;
  const scopes = new Map<symbol, string[]>();
  const inflight = new Map<string, AbortController>();
  const desiredKeys = () => {
    const keys = new Set<string>();
    const cap = settings.value?.lookupMaxEntries ?? 0;
    for (const ids of scopes.values()) {
      for (const id of ids) { if (keys.size < cap) { keys.add(id); } }
    }
    return keys;
  };
  const ensureSettings = () => {
    if (settings.value) { return Promise.resolve(settings.value); }
    if (settingsPending) { return settingsPending; }
    const captured = epoch;
    const owner = new AbortController(); settingsOwner = owner;
    const promise = loadIdentitySettings(owner.signal).then((value) => {
      if (captured !== epoch || owner.signal.aborted) { throw new DOMException("Obsolete directory settings", "AbortError"); }
      settings.value = value; unsupported.value = false; return value;
    }).catch((failure: unknown) => {
      if (captured === epoch && !owner.signal.aborted) { error.value = message(failure); unsupported.value = failure instanceof UnsupportedIdentityDirectory; }
      throw failure;
    }).finally(() => { if (settingsPending === promise) { settingsPending = undefined; } });
    settingsPending = promise; return promise;
  };
  const cancelPage = () => { pageGeneration += 1; pageOwner?.abort(); loading.value = false; };
  const fetchPage = async (query: IdentityQuery) => {
    cancelPage(); const generation = pageGeneration; const captured = epoch;
    const owner = new AbortController(); pageOwner = owner;
    items.value = []; total.value = null; loading.value = true; error.value = null;
    try {
      const config = await ensureSettings();
      if (generation !== pageGeneration || captured !== epoch) { return; }
      const result = await loadIdentityPage(query, config.pageSize, owner.signal);
      if (generation === pageGeneration && captured === epoch && !owner.signal.aborted) { items.value = result.items; total.value = result.total; }
    } catch (failure) {
      if (generation === pageGeneration && captured === epoch && !owner.signal.aborted) {
        error.value = message(failure); unsupported.value = failure instanceof UnsupportedIdentityDirectory;
      }
    } finally { if (generation === pageGeneration && captured === epoch) { loading.value = false; } }
  };
  const pump = () => {
    if (!settings.value) { return; }
    const desired = desiredKeys();
    for (const [key, owner] of inflight) { if (!desired.has(key)) { owner.abort(); } }
    for (const key of desired) {
      if (inflight.size >= settings.value.lookupConcurrency) { break; }
      if (cache.value.has(key) || lookupErrors.value.has(key) || inflight.has(key)) { continue; }
      const owner = new AbortController(); const captured = epoch; inflight.set(key, owner);
      void loadIdentityPage({ page: 1, view: "all", search: "", clientType: "all", order: "identity_asc" }, 1, owner.signal, key)
        .then((result) => {
          if (captured !== epoch || owner.signal.aborted || !desiredKeys().has(key)) { return; }
          cache.value.delete(key); cache.value.set(key, result.items[0] ?? null);
          const cap = settings.value?.lookupMaxEntries ?? 0;
          while (cache.value.size > cap) { const oldest = cache.value.keys().next().value; if (oldest !== undefined) { cache.value.delete(oldest); } }
        }).catch((failure: unknown) => {
          if (captured === epoch && !owner.signal.aborted) { lookupErrors.value.set(key, message(failure));
            while (lookupErrors.value.size > (settings.value?.lookupMaxEntries ?? 0)) { const oldest = lookupErrors.value.keys().next().value; if (oldest !== undefined) { lookupErrors.value.delete(oldest); } } }
        }).finally(() => { if (inflight.get(key) === owner) { inflight.delete(key); pump(); } });
    }
  };
  const setVisible = async (scope: symbol, ids: string[]) => {
    const captured = epoch;
    try {
      const config = await ensureSettings();
      if (captured !== epoch || !scopes.has(scope)) { return; }
      const previous = new Set(scopes.get(scope));
      const next = [...new Set(ids.map(normalizeIdentity).filter(Boolean))].slice(0, config.lookupMaxEntries);
      for (const key of next) {
        if (!previous.has(key)) { cache.value.delete(key); lookupErrors.value.delete(key); }
      }
      scopes.set(scope, next); pump();
    } catch { /* Directory errors are exposed independently; unrelated screens remain usable. */ }
  };
  const refreshVisible = () => {
    for (const key of desiredKeys()) {
      cache.value.delete(key); lookupErrors.value.delete(key); inflight.get(key)?.abort();
    }
    pump();
  };
  const register = () => { const scope = Symbol("visible-identities"); scopes.set(scope, []); return scope; };
  const unregister = (scope: symbol) => { scopes.delete(scope); pump(); };
  const lookup = (id?: string) => id ? cache.value.get(normalizeIdentity(id)) ?? undefined : undefined;
  const invalidate = () => {
    epoch += 1; cancelPage(); settingsOwner?.abort(); settingsPending = undefined;
    for (const owner of inflight.values()) { owner.abort(); } inflight.clear();
    cache.value.clear(); lookupErrors.value.clear(); items.value = []; total.value = null;
    error.value = null; unsupported.value = false;
    revision.value += 1;
    pump();
  };
  watch(() => connection.requestIdentity, () => { settings.value = null; invalidate(); }, { flush: "sync" });
  return { revision, settings, items, total, loading, error, unsupported, cache, lookupErrors, ensureSettings, fetchPage, cancelPage, register, setVisible, unregister, lookup, invalidate, refreshVisible };
});
