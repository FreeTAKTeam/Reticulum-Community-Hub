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

export interface EmergencyActionMessageApiRecord {
  callsign?: string | null;
  subject_type?: string | null;
  team_member_uid?: string | null;
  team_uid?: string | null;
  reported_by?: string | null;
  reported_at?: string | null;
  ttl_seconds?: number | null;
  notes?: string | null;
  confidence?: number | null;
  source?:
    | {
        rns_identity?: string | null;
        display_name?: string | null;
      }
    | null;
  overall_status?: string | null;
  security_status?: string | null;
  capability_status?: string | null;
  preparedness_status?: string | null;
  medical_status?: string | null;
  mobility_status?: string | null;
  comms_status?: string | null;
}

export interface EmergencyActionMessageUpsertPayload {
  callsign: string;
  team_member_uid: string;
  team_uid: string;
  reported_by?: string;
  reported_at?: string;
  ttl_seconds?: number;
  notes?: string;
  confidence?: number;
  source?: {
    rns_identity?: string;
    display_name?: string;
  };
  security_status?: string;
  capability_status?: string;
  preparedness_status?: string;
  medical_status?: string;
  mobility_status?: string;
  comms_status?: string;
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

const asText = (value: unknown): string | null => {
  if (value === null || value === undefined) {
    return null;
  }
  const text = String(value).trim();
  return text || null;
};

const asNumber = (value: unknown): number | null => {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const resolveSourceText = (
  source:
    | string
    | null
    | undefined
    | {
        rns_identity?: string | null;
        display_name?: string | null;
      }
): string | null => {
  if (typeof source === "string") {
    return asText(source);
  }
  if (!source || typeof source !== "object") {
    return null;
  }
  return asText(source.display_name) ?? asText(source.rns_identity);
};

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

export const toEmergencyActionMessageRecord = (
  record: EmergencyActionMessageApiRecord | EmergencyActionMessageRecord
): EmergencyActionMessageRecord => {
  const raw = record as Record<string, unknown>;
  const source = resolveSourceText(raw.source as string | { rns_identity?: string | null; display_name?: string | null } | null | undefined);
  const capabilityStatus =
    asText(raw.capabilityStatus) ??
    asText(raw.securityCapability) ??
    asText(raw.capability_status);

  return {
    callsign: asText(raw.callsign),
    subjectType: asText(raw.subjectType) ?? asText(raw.subject_type) ?? "member",
    subjectId: asText(raw.subjectId) ?? asText(raw.team_member_uid),
    teamId: asText(raw.teamId) ?? asText(raw.team_uid),
    reportedBy: asText(raw.reportedBy) ?? asText(raw.reported_by),
    reportedAt: asText(raw.reportedAt) ?? asText(raw.reported_at),
    ttlSeconds: asNumber(raw.ttlSeconds) ?? asNumber(raw.ttl_seconds),
    notes: asText(raw.notes),
    confidence: asNumber(raw.confidence),
    source,
    overallStatus: asText(raw.overallStatus) ?? asText(raw.overall_status),
    securityStatus: asText(raw.securityStatus) ?? asText(raw.security_status),
    capabilityStatus,
    securityCapability: asText(raw.securityCapability),
    preparednessStatus: asText(raw.preparednessStatus) ?? asText(raw.preparedness_status),
    medicalStatus: asText(raw.medicalStatus) ?? asText(raw.medical_status),
    mobilityStatus: asText(raw.mobilityStatus) ?? asText(raw.mobility_status),
    commsStatus: asText(raw.commsStatus) ?? asText(raw.comms_status)
  };
};

export const toEmergencyActionMessageUpsertPayload = (
  record: EmergencyActionMessageRecord
): EmergencyActionMessageUpsertPayload => {
  const callsign = asText(record.callsign) ?? "";
  const teamMemberUid = asText(record.subjectId) ?? "";
  const teamUid = asText(record.teamId) ?? "";
  const reportedBy = asText(record.reportedBy);
  const reportedAt = asText(record.reportedAt);
  const notes = asText(record.notes);
  const sourceIdentity = asText(record.source);
  const confidence = asNumber(record.confidence);
  const ttlSecondsValue = asNumber(record.ttlSeconds);
  const ttlSeconds = ttlSecondsValue === null ? null : Math.trunc(ttlSecondsValue);
  const capabilityStatus =
    asText(record.capabilityStatus) ??
    asText(record.securityCapability) ??
    "Unknown";

  const payload: EmergencyActionMessageUpsertPayload = {
    callsign,
    team_member_uid: teamMemberUid,
    team_uid: teamUid,
    security_status: asText(record.securityStatus) ?? "Unknown",
    capability_status: capabilityStatus,
    preparedness_status: asText(record.preparednessStatus) ?? "Unknown",
    medical_status: asText(record.medicalStatus) ?? "Unknown",
    mobility_status: asText(record.mobilityStatus) ?? "Unknown",
    comms_status: asText(record.commsStatus) ?? "Unknown"
  };

  if (reportedBy) {
    payload.reported_by = reportedBy;
  }
  if (reportedAt) {
    payload.reported_at = reportedAt;
  }
  if (notes) {
    payload.notes = notes;
  }
  if (confidence !== null) {
    payload.confidence = confidence;
  }
  if (ttlSeconds !== null && ttlSeconds >= 0) {
    payload.ttl_seconds = ttlSeconds;
  }
  if (sourceIdentity) {
    payload.source = { rns_identity: sourceIdentity };
  }

  return payload;
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
