import type { RouteLocationNormalized } from "vue-router";
import { watch } from "vue";
import { get } from "../api/client";
import type { ApiError } from "../api/client";
import { endpoints } from "../api/endpoints";
import { useConnectionStore } from "../stores/connection";

type Connection = ReturnType<typeof useConnectionStore>;
const restorations = new WeakMap<Connection, { identity: string; pending: Promise<boolean> }>();
const PUBLIC_ROUTES = new Set(["connect", "about"]);

const restoreRememberedSession = (connection: Connection): Promise<boolean> => {
  if (connection.hasActiveAuthSession) { return Promise.resolve(true); }
  if (!connection.rememberSecrets || connection.authMode === "none" ||
      !connection.hasValidAuthConfig() || connection.authStatus === "unauthenticated") {
    return Promise.resolve(false);
  }
  const identity = connection.requestIdentity;
  const existing = restorations.get(connection);
  if (existing?.identity === identity) { return existing.pending; }
  const controller = new AbortController();
  const stopWatching = watch(() => connection.requestIdentity, () => controller.abort(), { flush: "sync" });
  const pending = (async () => {
    try {
      await get(endpoints.status, { retries: 0, timeoutMs: 10000, suppressAuthStatus: true, signal: controller.signal });
      return connection.markAuthenticated(identity);
    } catch (failure) {
      if (identity === connection.requestIdentity) {
        const error = failure as ApiError;
        const rejected = error.status === 401 || error.status === 403;
        connection.setAuthStatus(rejected ? "unauthenticated" : "unknown",
          rejected ? "Saved credentials were rejected. Log in again." : "Unable to validate saved credentials. Try logging in again.");
      }
      return false;
    } finally {
      stopWatching();
    }
  })();
  restorations.set(connection, { identity, pending });
  return pending;
};

export const requireSession = async (to: RouteLocationNormalized) => {
  if (PUBLIC_ROUTES.has(String(to.name ?? "")) || to.path.startsWith("/Help") || to.path.startsWith("/Examples")) {
    return true;
  }
  const connection = useConnectionStore();
  await restoreRememberedSession(connection);
  return connection.hasActiveAuthSession ? true : { path: "/connect", query: { redirect: to.fullPath } };
};
