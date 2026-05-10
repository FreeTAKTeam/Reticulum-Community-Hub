import { del as deleteRequest } from "../../api/client";
import { patch as patchRequest } from "../../api/client";
import { post } from "../../api/client";
import { put } from "../../api/client";
import { endpoints } from "../../api/endpoints";
import type { MissionChangeRaw } from "../../types/missions/raw";
import type { MissionRaw } from "../../types/missions/raw";

export interface MissionDraftPayload {
  mission_name: string;
  mission_status: string;
  topic_id?: string | null;
  description?: string;
  path?: string | null;
  classification?: string | null;
  tool?: string | null;
  keywords?: string[];
  parent_uid?: string | null;
  feeds?: string[];
  default_role?: string | null;
  mission_priority?: number | null;
  owner_role?: string | null;
  token?: string | null;
  invite_only?: boolean;
  expiration?: string | null;
  mission_rde_role?: string | null;
  zones?: string[];
  asset_uids?: string[];
}

export interface MissionReferenceSyncPayload {
  missionUid: string;
  selectedTeamUid?: string;
  linkedTeamUids?: string[];
  selectedZoneUids?: string[];
  committedZoneUids?: string[];
}

export const useMissionActions = () => {
  const createMission = async (payload: MissionDraftPayload): Promise<MissionRaw> => {
    return post<MissionRaw>(endpoints.r3aktMissions, payload);
  };

  const updateMission = async (missionUid: string, payload: MissionDraftPayload): Promise<void> => {
    await patchRequest(`${endpoints.r3aktMissions}/${encodeURIComponent(missionUid)}`, { patch: payload });
  };

  const broadcastMission = async (missionUid: string, sourceIdentity: string): Promise<MissionChangeRaw> => {
    return post<MissionChangeRaw>(endpoints.r3aktMissionChanges, {
      mission_uid: missionUid,
      name: "Mission broadcast",
      change_type: "ADD_CONTENT",
      notes: "Broadcast emitted from mission workspace",
      team_member_rns_identity: sourceIdentity,
      timestamp: new Date().toISOString()
    });
  };

  const syncMissionReferenceLinks = async (payload: MissionReferenceSyncPayload): Promise<void> => {
    const missionUid = payload.missionUid.trim();
    if (!missionUid) {
      return;
    }

    const selectedTeamUid = String(payload.selectedTeamUid ?? "").trim();
    const linkedTeamUids = (payload.linkedTeamUids ?? []).map((entry) => String(entry ?? "").trim()).filter(Boolean);
    const selectedZoneUids = new Set((payload.selectedZoneUids ?? []).map((entry) => String(entry ?? "").trim()).filter(Boolean));
    const committedZoneUids = new Set((payload.committedZoneUids ?? []).map((entry) => String(entry ?? "").trim()).filter(Boolean));

    const operations: Array<Promise<unknown>> = [];

    if (selectedTeamUid && !linkedTeamUids.includes(selectedTeamUid)) {
      operations.push(
        put(`${endpoints.r3aktTeams}/${encodeURIComponent(selectedTeamUid)}/missions/${encodeURIComponent(missionUid)}`)
      );
    }

    linkedTeamUids
      .filter((entry) => entry !== selectedTeamUid)
      .forEach((teamUid) => {
        operations.push(
          deleteRequest(`${endpoints.r3aktTeams}/${encodeURIComponent(teamUid)}/missions/${encodeURIComponent(missionUid)}`)
        );
      });

    const missionZonesBase = `${endpoints.r3aktMissions}/${encodeURIComponent(missionUid)}/zones`;

    [...selectedZoneUids]
      .filter((zoneUid) => !committedZoneUids.has(zoneUid))
      .forEach((zoneUid) => {
        operations.push(put(`${missionZonesBase}/${encodeURIComponent(zoneUid)}`));
      });

    [...committedZoneUids]
      .filter((zoneUid) => !selectedZoneUids.has(zoneUid))
      .forEach((zoneUid) => {
        operations.push(deleteRequest(`${missionZonesBase}/${encodeURIComponent(zoneUid)}`));
      });

    await Promise.all(operations);
  };

  return {
    createMission,
    updateMission,
    broadcastMission,
    syncMissionReferenceLinks
  };
};
