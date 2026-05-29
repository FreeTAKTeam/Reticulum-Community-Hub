import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { endpoints } from "../api/endpoints";
import { get } from "../api/client";
import type { EventEntry, StatusResponse, TeamMemberRecord } from "../api/types";
import type { MissionRaw } from "../types/missions/raw";
import { buildEventCallsignLookup } from "../utils/event-feed";
import { useConnectionStore } from "./connection";
import { useUsersStore } from "./users";

type StatusApiPayload = StatusResponse & {
  uptime_seconds?: number;
};

type EventApiPayload = {
  timestamp?: string;
  type?: string;
  message?: string;
  metadata?: Record<string, unknown>;
};

const isRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === "object" && !Array.isArray(value);

const toArray = <T>(value: unknown): T[] => (Array.isArray(value) ? (value as T[]) : []);

const normalizeStatus = (payload: StatusApiPayload): StatusResponse => {
  const uptime = payload.uptime ?? payload.uptime_seconds;
  const telemetry = payload.telemetry
    ? {
        ...payload.telemetry,
        total: payload.telemetry.total ?? payload.telemetry.ingest_count
      }
    : undefined;
  return {
    ...payload,
    uptime,
    telemetry
  };
};

const normalizeEvent = (payload: EventApiPayload): EventEntry => ({
  id: payload.timestamp ?? `${Date.now()}`,
  created_at: payload.timestamp,
  message: payload.message,
  level: "info",
  category: payload.type,
  metadata: payload.metadata ?? {}
});

const normalizeMissionStatus = (value: unknown): string => {
  const token = String(value ?? "")
    .trim()
    .toUpperCase()
    .replace(/[\s-]+/g, "_");
  if (!token) {
    return "";
  }
  if (token === "ACTIVE") {
    return "MISSION_ACTIVE";
  }
  return token.startsWith("MISSION_") ? token : `MISSION_${token}`;
};

const isActiveMission = (mission: MissionRaw): boolean => {
  return normalizeMissionStatus(mission.mission_status) === "MISSION_ACTIVE";
};

export const useDashboardStore = defineStore("dashboard", () => {
  const usersStore = useUsersStore();
  const status = ref<StatusResponse | null>(null);
  const activeMissions = ref<number | null>(null);
  const events = ref<EventEntry[]>([]);
  const teamMembers = ref<TeamMemberRecord[]>([]);
  const loading = ref(false);
  const eventCallsignLookup = computed(() =>
    buildEventCallsignLookup({
      teamMembers: teamMembers.value,
      clients: usersStore.clients,
      identities: usersStore.identities,
      remPeers: usersStore.remPeers
    })
  );

  const refresh = async () => {
    loading.value = true;
    const connectionStore = useConnectionStore();
    try {
      const response = await get<StatusApiPayload>(endpoints.status);
      status.value = normalizeStatus(isRecord(response) ? response : {});

      const [eventResponse, missionResponse, teamMemberResponse] = await Promise.allSettled([
        get<EventApiPayload[]>(endpoints.events),
        get<MissionRaw[]>(endpoints.r3aktMissions),
        get<TeamMemberRecord[]>(endpoints.r3aktTeamMembers),
        usersStore.fetchUsers()
      ]);

      if (eventResponse.status !== "fulfilled") {
        throw eventResponse.reason;
      }
      events.value = toArray<EventApiPayload>(eventResponse.value).map(normalizeEvent);

      if (missionResponse.status === "fulfilled") {
        activeMissions.value = toArray<MissionRaw>(missionResponse.value).filter(isActiveMission).length;
      } else {
        activeMissions.value = null;
      }
      if (teamMemberResponse.status === "fulfilled") {
        teamMembers.value = toArray<TeamMemberRecord>(teamMemberResponse.value);
      }
      connectionStore.setOnline();
    } finally {
      loading.value = false;
    }
  };

  const pushEvent = (event: EventApiPayload | EventEntry) => {
    const mapped = "timestamp" in event || "type" in event ? normalizeEvent(event as EventApiPayload) : (event as EventEntry);
    events.value = [mapped, ...events.value].slice(0, 50);
  };

  const updateStatus = (payload: StatusApiPayload) => {
    status.value = normalizeStatus(payload);
  };

  return {
    status,
    activeMissions,
    events,
    eventCallsignLookup,
    loading,
    refresh,
    pushEvent,
    updateStatus
  };
});
