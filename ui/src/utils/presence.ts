const DEFAULT_ACTIVE_WINDOW_MS = 5 * 60 * 1000;

const ONLINE_STATUSES = new Set(["active", "online", "joined"]);
const OFFLINE_STATUSES = new Set(["inactive", "offline", "stale", "blackholed", "banned"]);

const parseTimestamp = (value?: string | null): number | null => {
  if (!value) {
    return null;
  }
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) {
    return null;
  }
  return parsed;
};

const statusPresence = (status?: string | null): boolean | null => {
  const normalized = status?.trim().toLowerCase();
  if (!normalized) {
    return null;
  }
  if (ONLINE_STATUSES.has(normalized)) {
    return true;
  }
  if (OFFLINE_STATUSES.has(normalized)) {
    return false;
  }
  return null;
};

type PresenceOptions = {
  nowMs?: number;
  activeWindowMs?: number;
};

type PresenceInput = {
  status?: string | null;
  lastSeenAt?: string | null;
};

export const isRecentlySeen = (lastSeenAt?: string | null, options: PresenceOptions = {}): boolean => {
  const seenTimestamp = parseTimestamp(lastSeenAt);
  if (seenTimestamp === null) {
    return false;
  }
  const nowMs = options.nowMs ?? Date.now();
  const activeWindowMs = options.activeWindowMs ?? DEFAULT_ACTIVE_WINDOW_MS;
  return nowMs - seenTimestamp <= activeWindowMs;
};

export const isPresenceOnline = (input: PresenceInput, options: PresenceOptions = {}): boolean => {
  const statusOnline = statusPresence(input.status);
  if (statusOnline !== null) {
    return statusOnline;
  }
  return isRecentlySeen(input.lastSeenAt, options);
};

export const clientPresenceTag = (lastSeenAt?: string | null, options: PresenceOptions = {}): string => {
  return isRecentlySeen(lastSeenAt, options) ? "Active" : "Seen";
};
