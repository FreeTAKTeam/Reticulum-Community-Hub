import { del as deleteRequest } from "../../api/client";
import { patch as patchRequest } from "../../api/client";
import { post } from "../../api/client";
import { endpoints } from "../../api/endpoints";
import type { ChecklistRaw } from "../../types/missions/raw";

export const useChecklistActions = () => {
  const createChecklist = async (payload: Record<string, unknown>): Promise<ChecklistRaw> => {
    return post<ChecklistRaw>(endpoints.checklists, payload);
  };

  const createOfflineChecklist = async (payload: Record<string, unknown>): Promise<ChecklistRaw> => {
    return post<ChecklistRaw>(endpoints.checklistsOffline, payload);
  };

  const deleteChecklist = async (checklistUid: string): Promise<void> => {
    await deleteRequest(`${endpoints.checklists}/${encodeURIComponent(checklistUid)}`);
  };

  const linkChecklistMission = async (checklistUid: string, missionUid?: string): Promise<void> => {
    await patchRequest(`${endpoints.checklists}/${encodeURIComponent(checklistUid)}`, {
      patch: { mission_uid: missionUid?.trim() ? missionUid : null }
    });
  };

  const addChecklistTask = async (checklistUid: string, payload: Record<string, unknown>): Promise<void> => {
    await post(`${endpoints.checklists}/${encodeURIComponent(checklistUid)}/tasks`, payload);
  };

  const setChecklistTaskStatus = async (
    checklistUid: string,
    taskUid: string,
    userStatus: string,
    sourceIdentity: string
  ): Promise<void> => {
    await post(`${endpoints.checklists}/${encodeURIComponent(checklistUid)}/tasks/${encodeURIComponent(taskUid)}/status`, {
      user_status: userStatus,
      changed_by_team_member_rns_identity: sourceIdentity
    });
  };

  const editChecklistCell = async (
    checklistUid: string,
    taskUid: string,
    columnUid: string,
    value: string,
    sourceIdentity: string
  ): Promise<void> => {
    await patchRequest(
      `${endpoints.checklists}/${encodeURIComponent(checklistUid)}/tasks/${encodeURIComponent(taskUid)}/cells/${encodeURIComponent(columnUid)}`,
      {
        value,
        updated_by_team_member_rns_identity: sourceIdentity
      }
    );
  };

  const joinChecklist = async (checklistUid: string, sourceIdentity: string): Promise<void> => {
    await post(`${endpoints.checklists}/${encodeURIComponent(checklistUid)}/join`, {
      source_identity: sourceIdentity
    });
  };

  const uploadChecklist = async (checklistUid: string, sourceIdentity: string): Promise<void> => {
    await post(`${endpoints.checklists}/${encodeURIComponent(checklistUid)}/upload`, {
      source_identity: sourceIdentity
    });
  };

  const publishChecklist = async (checklistUid: string, missionFeedUid: string, sourceIdentity: string): Promise<void> => {
    await post(`${endpoints.checklists}/${encodeURIComponent(checklistUid)}/feeds/${encodeURIComponent(missionFeedUid)}`, {
      source_identity: sourceIdentity
    });
  };

  return {
    createChecklist,
    createOfflineChecklist,
    deleteChecklist,
    linkChecklistMission,
    addChecklistTask,
    setChecklistTaskStatus,
    editChecklistCell,
    joinChecklist,
    uploadChecklist,
    publishChecklist
  };
};
