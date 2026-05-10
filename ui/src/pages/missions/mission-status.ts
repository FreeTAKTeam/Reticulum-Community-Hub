export const MISSION_STATUS_ENUM = [
  "MISSION_ACTIVE",
  "MISSION_PENDING",
  "MISSION_COMPLETED_SUCCESS",
  "MISSION_COMPLETED_FAILED",
  "MISSION_DELETED"
] as const;

export type MissionStatusEnum = (typeof MISSION_STATUS_ENUM)[number];
export type MissionStatusTone = "active" | "pending" | "success" | "failed" | "deleted";

const MISSION_STATUS_ALIAS_MAP: Record<string, MissionStatusEnum> = {
  ACTIVE: "MISSION_ACTIVE",
  MISSION_ACTIVE: "MISSION_ACTIVE",
  PENDING: "MISSION_PENDING",
  MISSION_PENDING: "MISSION_PENDING",
  PLANNED: "MISSION_PENDING",
  MISSION_PLANNED: "MISSION_PENDING",
  STANDBY: "MISSION_PENDING",
  MISSION_STANDBY: "MISSION_PENDING",
  COMPLETE: "MISSION_COMPLETED_SUCCESS",
  COMPLETED: "MISSION_COMPLETED_SUCCESS",
  SUCCESS: "MISSION_COMPLETED_SUCCESS",
  MISSION_COMPLETE: "MISSION_COMPLETED_SUCCESS",
  MISSION_COMPLETED: "MISSION_COMPLETED_SUCCESS",
  MISSION_COMPLETED_SUCCESS: "MISSION_COMPLETED_SUCCESS",
  FAILED: "MISSION_COMPLETED_FAILED",
  FAILURE: "MISSION_COMPLETED_FAILED",
  ERROR: "MISSION_COMPLETED_FAILED",
  MISSION_FAILED: "MISSION_COMPLETED_FAILED",
  MISSION_FAILURE: "MISSION_COMPLETED_FAILED",
  MISSION_ERROR: "MISSION_COMPLETED_FAILED",
  IN_COMPLETE: "MISSION_COMPLETED_FAILED",
  INCOMPLETE: "MISSION_COMPLETED_FAILED",
  MISSION_IN_COMPLETE: "MISSION_COMPLETED_FAILED",
  MISSION_INCOMPLETE: "MISSION_COMPLETED_FAILED",
  MISSION_COMPLETED_FAILED: "MISSION_COMPLETED_FAILED",
  DELETE: "MISSION_DELETED",
  DELETED: "MISSION_DELETED",
  ARCHIVE: "MISSION_DELETED",
  ARCHIVED: "MISSION_DELETED",
  MISSION_DELETE: "MISSION_DELETED",
  MISSION_DELETED: "MISSION_DELETED",
  MISSION_ARCHIVE: "MISSION_DELETED",
  MISSION_ARCHIVED: "MISSION_DELETED"
};

export const toMissionStatusEnum = (value?: string | null): MissionStatusEnum => {
  const token = String(value ?? "")
    .trim()
    .toUpperCase()
    .replace(/[\s-]+/g, "_");
  if (!token) {
    return "MISSION_ACTIVE";
  }

  const mapped = MISSION_STATUS_ALIAS_MAP[token];
  if (mapped) {
    return mapped;
  }

  if (token.startsWith("MISSION_")) {
    return MISSION_STATUS_ENUM.includes(token as MissionStatusEnum) ? (token as MissionStatusEnum) : "MISSION_ACTIVE";
  }

  const prefixed = `MISSION_${token}` as MissionStatusEnum;
  return MISSION_STATUS_ENUM.includes(prefixed) ? prefixed : "MISSION_ACTIVE";
};

export const normalizeMissionStatus = (value?: string | null): string => {
  return toMissionStatusEnum(value).slice("MISSION_".length);
};

export const toMissionStatusValue = (value?: string | null): string => {
  return toMissionStatusEnum(value);
};

const MISSION_STATUS_LABEL_MAP: Record<MissionStatusEnum, string> = {
  MISSION_ACTIVE: "Active",
  MISSION_PENDING: "Pending",
  MISSION_COMPLETED_SUCCESS: "Success",
  MISSION_COMPLETED_FAILED: "Failed",
  MISSION_DELETED: "Deleted"
};

const MISSION_STATUS_TONE_MAP: Record<MissionStatusEnum, MissionStatusTone> = {
  MISSION_ACTIVE: "active",
  MISSION_PENDING: "pending",
  MISSION_COMPLETED_SUCCESS: "success",
  MISSION_COMPLETED_FAILED: "failed",
  MISSION_DELETED: "deleted"
};

export const getMissionStatusLabel = (value?: string | null): string => {
  return MISSION_STATUS_LABEL_MAP[toMissionStatusEnum(value)];
};

export const getMissionStatusTone = (value?: string | null): MissionStatusTone => {
  return MISSION_STATUS_TONE_MAP[toMissionStatusEnum(value)];
};
