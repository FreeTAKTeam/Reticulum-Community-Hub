import { endpoints } from "../api/endpoints";

export const resolveChecklistCreateEndpoint = (localDraft = false): string => {
  return localDraft ? endpoints.checklistsOffline : endpoints.checklists;
};
