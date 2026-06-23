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
  id?: string;
  timestamp?: string;
  created_at?: string;
  type?: string;
  category?: string;
  message?: string;
  level?: string;
  metadata?: Record<string, unknown>;
};

export const EVENT_FEED_MAX_EVENTS = 200;

const isRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === "object" && !Array.isArray(value);

const toArray = <T>(value: unknown): T[] => (Array.isArray(value) ? (value as T[]) : []);

const toKeyPart = (value: unknown): string =>
  String(value ?? "")
    .trim()
    .toLowerCase();

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
  id: payload.id,
  created_at: payload.created_at ?? payload.timestamp,
  message: payload.message,
  level: payload.level ?? "info",
  category: payload.category ?? payload.type,
  metadata: payload.metadata ?? {}
});

const eventTime = (event: EventEntry): number => {
  const parsed = Date.parse(event.created_at ?? "");
  return Number.isNaN(parsed) ? 0 : parsed;
};

const metadataString = (metadata: Record<string, unknown> | undefined, key: string): string =>
  String(metadata?.[key] ?? "").trim();

const deliveryMessageId = (event: EventEntry): string => {
  const metadata = event.metadata;
  const directId = metadataString(metadata, "MessageID") || metadataString(metadata, "message_id");
  if (directId) {
    return directId;
  }
  const deliveryMetadata = metadata?.DeliveryMetadata;
  if (isRecord(deliveryMetadata)) {
    return metadataString(deliveryMetadata, "message_id");
  }
  return "";
};

const isDeliveryFailureEvent = (event: EventEntry): boolean =>
  toKeyPart(event.category) === "message_delivery_failed" ||
  toKeyPart(event.metadata?.original_event_type) === "message_delivery_failed";

const supersedesDeliveryFailure = (event: EventEntry): boolean =>
  toKeyPart(event.category) === "message_delivery_superseded" ||
  event.metadata?.delivery_failure_superseded === true;

const isDeliveryRecoveryEvent = (event: EventEntry): boolean => {
  const category = toKeyPart(event.category);
  if (supersedesDeliveryFailure(event)) {
    return true;
  }
  if (
    ![
      "message_delivered",
      "message_delivery_retrying",
      "message_propagated",
      "message_propagation_queued",
      "message_sent"
    ].includes(category)
  ) {
    return false;
  }
  return deliveryMessageId(event) !== "" && toKeyPart(event.metadata?.State) !== "failed";
};

export const eventEntryKey = (event: EventEntry): string => {
  const id = toKeyPart(event.id);
  if (id) {
    return id;
  }
  return [event.created_at, event.category, event.message].map(toKeyPart).join("|");
};

const mergeEventLists = (current: EventEntry[], incoming: EventEntry[]): EventEntry[] => {
  const merged = new Map<string, EventEntry>();
  for (const event of [...current, ...incoming]) {
    const messageId = deliveryMessageId(event);
    const currentEventTime = eventTime(event);
    if (isDeliveryFailureEvent(event) && messageId) {
      const alreadyRecovered = [...merged.values()].some(
        (existing) =>
          isDeliveryRecoveryEvent(existing) &&
          deliveryMessageId(existing) === messageId &&
          eventTime(existing) >= currentEventTime
      );
      if (alreadyRecovered) {
        continue;
      }
    }
    if (isDeliveryRecoveryEvent(event)) {
      const messageId = deliveryMessageId(event);
      if (messageId) {
        for (const [key, existing] of merged) {
          if (
            isDeliveryFailureEvent(existing) &&
            deliveryMessageId(existing) === messageId &&
            eventTime(existing) <= currentEventTime
          ) {
            merged.delete(key);
          }
        }
      }
    }
    merged.set(eventEntryKey(event), event);
  }
  return [...merged.values()]
    .sort((left, right) => eventTime(right) - eventTime(left))
    .slice(0, EVENT_FEED_MAX_EVENTS);
};

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

      const [missionResponse, teamMemberResponse] = await Promise.allSettled([
        get<MissionRaw[]>(endpoints.r3aktMissions),
        get<TeamMemberRecord[]>(endpoints.r3aktTeamMembers),
        usersStore.fetchUsers()
      ]);

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
    events.value = mergeEventLists(events.value, [mapped]);
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
