import { computed } from "vue";
import { watch } from "vue";
import { useRoute } from "vue-router";
import { useRouter } from "vue-router";
import { useMissionWorkspaceStore } from "../../stores/missionWorkspace";

const queryText = (value: unknown): string => {
  if (Array.isArray(value)) {
    return String(value[0] ?? "").trim();
  }
  return String(value ?? "").trim();
};

export const useMissionScope = () => {
  const route = useRoute();
  const router = useRouter();
  const workspace = useMissionWorkspaceStore();

  const selectedMissionUid = computed({
    get: () => workspace.selectedMissionUid,
    set: (value: string) => {
      workspace.setSelectedMissionUid(value);
      workspace.syncRouteQuery(route, router);
    }
  });

  watch(
    () => route.query.mission_uid,
    (value) => {
      const next = queryText(value);
      if (!next) {
        if (!workspace.selectedMissionUid) {
          workspace.restorePersistedSelection();
        }
        return;
      }
      if (next !== workspace.selectedMissionUid) {
        workspace.setSelectedMissionUid(next);
      }
    },
    { immediate: true }
  );

  watch(
    () => workspace.selectedMissionUid,
    () => {
      workspace.syncRouteQuery(route, router);
    },
    { immediate: true }
  );

  watch(
    () => workspace.missions,
    () => {
      workspace.ensureSelectedMissionExists();
      workspace.syncRouteQuery(route, router);
    },
    { immediate: true }
  );

  return {
    selectedMissionUid
  };
};
