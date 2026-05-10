import { computed } from "vue";
import { watch } from "vue";
import type { LocationQueryRaw } from "vue-router";
import type { RouteLocationNormalizedLoaded } from "vue-router";
import type { Router } from "vue-router";

const readQueryValue = (value: unknown): string => {
  if (Array.isArray(value)) {
    return String(value[0] ?? "");
  }
  return String(value ?? "");
};

interface UseRouteQueryScopeOptions {
  route: RouteLocationNormalizedLoaded;
  router: Router;
  key: string;
  defaultValue?: string;
}

export const useRouteQueryScope = (options: UseRouteQueryScopeOptions) => {
  const queryValue = computed<string>({
    get: () => {
      const raw = readQueryValue(options.route.query[options.key]);
      return raw || options.defaultValue || "";
    },
    set: (value: string) => {
      const nextQuery: LocationQueryRaw = { ...options.route.query };
      if (value) {
        nextQuery[options.key] = value;
      } else {
        delete nextQuery[options.key];
      }
      options.router.replace({ query: nextQuery }).catch(() => undefined);
    }
  });

  watch(
    () => options.route.query[options.key],
    (value) => {
      const next = readQueryValue(value) || options.defaultValue || "";
      if (queryValue.value !== next) {
        queryValue.value = next;
      }
    }
  );

  return {
    queryValue
  };
};
