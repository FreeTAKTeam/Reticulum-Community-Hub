import { del as deleteRequest } from "../../api/client";
import { post } from "../../api/client";
import { put } from "../../api/client";
import { endpoints } from "../../api/endpoints";

export const useZoneActions = () => {
  const createZone = async (payload: Record<string, unknown>): Promise<{ zone_id?: string }> => {
    return post<{ zone_id?: string }>(endpoints.zones, payload);
  };

  const linkZoneToMission = async (missionUid: string, zoneUid: string): Promise<void> => {
    await put(`${endpoints.r3aktMissions}/${encodeURIComponent(missionUid)}/zones/${encodeURIComponent(zoneUid)}`);
  };

  const unlinkZoneFromMission = async (missionUid: string, zoneUid: string): Promise<void> => {
    await deleteRequest(`${endpoints.r3aktMissions}/${encodeURIComponent(missionUid)}/zones/${encodeURIComponent(zoneUid)}`);
  };

  const commitMissionZones = async (
    missionUid: string,
    selectedZoneUids: string[],
    committedZoneUids: string[]
  ): Promise<void> => {
    const selected = new Set(selectedZoneUids.map((entry) => String(entry ?? "").trim()).filter(Boolean));
    const committed = new Set(committedZoneUids.map((entry) => String(entry ?? "").trim()).filter(Boolean));

    const toLink = [...selected].filter((entry) => !committed.has(entry));
    const toUnlink = [...committed].filter((entry) => !selected.has(entry));

    await Promise.all([
      ...toLink.map((zoneUid) =>
        put(`${endpoints.r3aktMissions}/${encodeURIComponent(missionUid)}/zones/${encodeURIComponent(zoneUid)}`)
      ),
      ...toUnlink.map((zoneUid) =>
        deleteRequest(`${endpoints.r3aktMissions}/${encodeURIComponent(missionUid)}/zones/${encodeURIComponent(zoneUid)}`)
      )
    ]);
  };

  return {
    createZone,
    linkZoneToMission,
    unlinkZoneFromMission,
    commitMissionZones
  };
};
