import { get } from "../../api/client";
import { endpoints } from "../../api/endpoints";

const downloadBlob = (filename: string, payload: string, contentType: string): void => {
  const blob = new Blob([payload], { type: contentType });
  const href = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(href);
};

export const useAuditExportActions = () => {
  const buildTimestampTag = (): string => new Date().toISOString().replace(/[^0-9]/g, "").slice(0, 14);

  const downloadJson = (filename: string, payload: unknown): void => {
    downloadBlob(filename, JSON.stringify(payload, null, 2), "application/json");
  };

  const downloadText = (filename: string, payload: string, contentType = "text/plain"): void => {
    downloadBlob(filename, payload, contentType);
  };

  const exportMissions = (missions: unknown): void => {
    downloadJson(`missions-${buildTimestampTag()}.json`, missions);
  };

  const exportMissionAudit = (missionUid: string, auditPayload: unknown): void => {
    downloadJson(`mission-audit-${missionUid}.json`, auditPayload);
  };

  const exportChecklistProgress = (checklistUid: string, checklistPayload: unknown): void => {
    downloadJson(`checklist-progress-${checklistUid}.json`, checklistPayload);
  };

  const exportSnapshots = async (missionUid: string): Promise<void> => {
    const payload = await get<Array<{ aggregate_uid?: string } & Record<string, unknown>>>(endpoints.r3aktSnapshots);
    const filtered = payload.filter((entry) => String(entry.aggregate_uid ?? "").trim() === missionUid);
    downloadJson(`mission-snapshots-${missionUid}.json`, filtered);
  };

  return {
    buildTimestampTag,
    downloadJson,
    downloadText,
    exportMissions,
    exportMissionAudit,
    exportChecklistProgress,
    exportSnapshots
  };
};
