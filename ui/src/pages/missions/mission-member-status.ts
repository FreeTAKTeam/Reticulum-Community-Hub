export const MISSION_MEMBER_STATUS_DIMENSIONS = [
  { key: "securityStatus", label: "Security" },
  { key: "capabilityStatus", label: "Capability" },
  { key: "preparednessStatus", label: "Preparedness" },
  { key: "medicalStatus", label: "Medical" },
  { key: "mobilityStatus", label: "Mobility" },
  { key: "commsStatus", label: "Comms" }
] as const;

export type MissionMemberStatusKey = (typeof MISSION_MEMBER_STATUS_DIMENSIONS)[number]["key"];
export type EamStatus = "Green" | "Yellow" | "Red" | "Unknown";
export const MISSION_MEMBER_STATUS_CYCLE: EamStatus[] = ["Unknown", "Green", "Yellow", "Red"];

export interface EmergencyActionMessageRecord {
  callsign?: string | null;
  subjectType?: string | null;
  subjectId?: string | null;
  teamId?: string | null;
  reportedBy?: string | null;
  reportedAt?: string | null;
  ttlSeconds?: number | null;
  notes?: string | null;
  confidence?: number | null;
  source?: string | null;
  overallStatus?: string | null;
  securityStatus?: string | null;
  capabilityStatus?: string | null;
  securityCapability?: string | null;
  preparednessStatus?: string | null;
  medicalStatus?: string | null;
  mobilityStatus?: string | null;
  commsStatus?: string | null;
}

export interface MissionMemberStatusSummary {
  overallStatus: EamStatus;
  securityStatus: EamStatus;
  capabilityStatus: EamStatus;
  preparednessStatus: EamStatus;
  medicalStatus: EamStatus;
  mobilityStatus: EamStatus;
  commsStatus: EamStatus;
  scorePercent: number;
  reportedAt: string;
  ttlSeconds: number | null;
  isExpired: boolean;
}

const STATUS_WEIGHT: Record<EamStatus, number> = {
  Green: 1,
  Yellow: 0.5,
  Red: 0,
  Unknown: 0
};

const STATUS_SEVERITY: Record<EamStatus, number> = {
  Red: 3,
  Yellow: 2,
  Unknown: 1,
  Green: 0
};

const UNKNOWN_STATUS: EamStatus = "Unknown";

const normalizeStatus = (value: unknown): EamStatus => {
  const normalized = String(value ?? "").trim().toLowerCase();
  if (normalized === "green") {
    return "Green";
  }
  if (normalized === "yellow") {
    return "Yellow";
  }
  if (normalized === "red") {
    return "Red";
  }
  return "Unknown";
};

const getStatusFromRecord = (
  record: EmergencyActionMessageRecord | null | undefined,
  key: MissionMemberStatusKey
): EamStatus => {
  if (!record) {
    return UNKNOWN_STATUS;
  }
  if (key === "capabilityStatus") {
    return normalizeStatus(record.capabilityStatus ?? record.securityCapability);
  }
  return normalizeStatus(record[key]);
};

export const deriveMissionMemberOverallStatus = (statuses: EamStatus[]): EamStatus => {
  if (statuses.some((status) => status === "Red")) {
    return "Red";
  }
  if (statuses.some((status) => status === "Yellow")) {
    return "Yellow";
  }
  if (statuses.every((status) => status === "Green")) {
    return "Green";
  }
  return "Unknown";
};

const getScorePercent = (statuses: EamStatus[]): number => {
  const weighted = statuses.reduce((sum, status) => sum + STATUS_WEIGHT[status], 0);
  return Math.round((weighted / statuses.length) * 100);
};

const isExpiredRecord = (
  record: EmergencyActionMessageRecord | null | undefined,
  referenceTimeMs: number
): boolean => {
  if (!record) {
    return false;
  }
  if (record.ttlSeconds === null || record.ttlSeconds === undefined || record.ttlSeconds === "") {
    return false;
  }
  const ttlSeconds = Number(record.ttlSeconds);
  if (!Number.isFinite(ttlSeconds) || ttlSeconds < 0) {
    return false;
  }
  const reportedAtMs = Date.parse(String(record.reportedAt ?? ""));
  if (Number.isNaN(reportedAtMs)) {
    return false;
  }
  return reportedAtMs + ttlSeconds * 1000 <= referenceTimeMs;
};

export const createUnknownMissionMemberStatus = (): MissionMemberStatusSummary => ({
  overallStatus: "Unknown",
  securityStatus: "Unknown",
  capabilityStatus: "Unknown",
  preparednessStatus: "Unknown",
  medicalStatus: "Unknown",
  mobilityStatus: "Unknown",
  commsStatus: "Unknown",
  scorePercent: 0,
  reportedAt: "",
  ttlSeconds: null,
  isExpired: false
});

export const toMissionMemberStatusSummary = (
  record: EmergencyActionMessageRecord | null | undefined,
  options: { referenceTimeMs?: number } = {}
): MissionMemberStatusSummary => {
  if (!record) {
    return createUnknownMissionMemberStatus();
  }

  const referenceTimeMs = options.referenceTimeMs ?? Date.now();
  const isExpired = isExpiredRecord(record, referenceTimeMs);
  if (isExpired) {
    return {
      ...createUnknownMissionMemberStatus(),
      reportedAt: String(record.reportedAt ?? "").trim(),
      ttlSeconds:
        record.ttlSeconds === null || record.ttlSeconds === undefined || record.ttlSeconds === ""
          ? null
          : Number.isFinite(Number(record.ttlSeconds))
            ? Number(record.ttlSeconds)
            : null,
      isExpired: true
    };
  }

  const securityStatus = getStatusFromRecord(record, "securityStatus");
  const capabilityStatus = getStatusFromRecord(record, "capabilityStatus");
  const preparednessStatus = getStatusFromRecord(record, "preparednessStatus");
  const medicalStatus = getStatusFromRecord(record, "medicalStatus");
  const mobilityStatus = getStatusFromRecord(record, "mobilityStatus");
  const commsStatus = getStatusFromRecord(record, "commsStatus");
  const dimensionStatuses = [
    securityStatus,
    capabilityStatus,
    preparednessStatus,
    medicalStatus,
    mobilityStatus,
    commsStatus
  ];
  const normalizedOverall = normalizeStatus(record.overallStatus);
  const overallStatus =
    normalizedOverall === "Unknown" ? deriveMissionMemberOverallStatus(dimensionStatuses) : normalizedOverall;

  return {
    overallStatus,
    securityStatus,
    capabilityStatus,
    preparednessStatus,
    medicalStatus,
    mobilityStatus,
    commsStatus,
    scorePercent: getScorePercent(dimensionStatuses),
    reportedAt: String(record.reportedAt ?? "").trim(),
    ttlSeconds:
      record.ttlSeconds === null || record.ttlSeconds === undefined || record.ttlSeconds === ""
        ? null
        : Number.isFinite(Number(record.ttlSeconds))
          ? Number(record.ttlSeconds)
          : null,
    isExpired: false
  };
};

export const getMissionMemberStatusTone = (status: EamStatus): string => {
  if (status === "Green") {
    return "green";
  }
  if (status === "Yellow") {
    return "yellow";
  }
  if (status === "Red") {
    return "red";
  }
  return "unknown";
};

export const compareMissionMemberStatuses = (left: EamStatus, right: EamStatus): number =>
  STATUS_SEVERITY[right] - STATUS_SEVERITY[left];

export const cycleMissionMemberStatus = (status: EamStatus): EamStatus => {
  const currentIndex = MISSION_MEMBER_STATUS_CYCLE.indexOf(status);
  const nextIndex = currentIndex < 0 ? 0 : (currentIndex + 1) % MISSION_MEMBER_STATUS_CYCLE.length;
  return MISSION_MEMBER_STATUS_CYCLE[nextIndex];
};
