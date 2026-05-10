import { del as deleteRequest } from "../../api/client";
import { post } from "../../api/client";
import { endpoints } from "../../api/endpoints";
import type { AssetRaw } from "../../types/missions/raw";
import type { AssignmentRaw } from "../../types/missions/raw";

export const useAssetAssignmentActions = () => {
  const upsertAsset = async (payload: Record<string, unknown>): Promise<AssetRaw> => {
    return post<AssetRaw>(endpoints.r3aktAssets, payload);
  };

  const deleteAsset = async (assetUid: string): Promise<void> => {
    await deleteRequest(`${endpoints.r3aktAssets}/${encodeURIComponent(assetUid)}`);
  };

  const upsertAssignment = async (payload: Record<string, unknown>): Promise<AssignmentRaw> => {
    return post<AssignmentRaw>(endpoints.r3aktAssignments, payload);
  };

  const revokeAssignment = async (payload: Record<string, unknown>): Promise<AssignmentRaw> => {
    return post<AssignmentRaw>(endpoints.r3aktAssignments, payload);
  };

  return {
    upsertAsset,
    deleteAsset,
    upsertAssignment,
    revokeAssignment
  };
};
