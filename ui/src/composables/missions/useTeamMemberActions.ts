import { del as deleteRequest } from "../../api/client";
import { post } from "../../api/client";
import { put } from "../../api/client";
import { endpoints } from "../../api/endpoints";
import type { TeamMemberRaw } from "../../types/missions/raw";
import type { TeamRaw } from "../../types/missions/raw";

export const useTeamMemberActions = () => {
  const linkTeamToMission = async (teamUid: string, missionUid: string): Promise<void> => {
    await put(`${endpoints.r3aktTeams}/${encodeURIComponent(teamUid)}/missions/${encodeURIComponent(missionUid)}`);
  };

  const unlinkTeamFromMission = async (teamUid: string, missionUid: string): Promise<void> => {
    await deleteRequest(`${endpoints.r3aktTeams}/${encodeURIComponent(teamUid)}/missions/${encodeURIComponent(missionUid)}`);
  };

  const createMissionTeam = async (payload: Record<string, unknown>): Promise<TeamRaw> => {
    return post<TeamRaw>(endpoints.r3aktTeams, payload);
  };

  const assignMemberToTeam = async (payload: Record<string, unknown>): Promise<TeamMemberRaw> => {
    return post<TeamMemberRaw>(endpoints.r3aktTeamMembers, payload);
  };

  return {
    linkTeamToMission,
    unlinkTeamFromMission,
    createMissionTeam,
    assignMemberToTeam
  };
};
