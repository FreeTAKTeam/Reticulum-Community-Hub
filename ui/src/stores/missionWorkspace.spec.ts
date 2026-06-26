import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { endpoints } from "../api/endpoints";
import { useMissionWorkspaceStore } from "./missionWorkspace";

const { getMock } = vi.hoisted(() => ({
  getMock: vi.fn()
}));

vi.mock("../api/client", () => ({
  get: getMock
}));

const missionUid = "mission-wrapped-domain";
const teamUid = "team-wrapped-domain";
const memberUid = "member-wrapped-domain";
const assetUid = "asset-wrapped-domain";
const assignmentUid = "assignment-wrapped-domain";

const wrapped = <T>(value: T[]) => ({ value, Count: value.length });

describe("mission workspace store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    localStorage.clear();
    getMock.mockReset();
    getMock.mockImplementation((path: string) => {
      switch (path) {
        case endpoints.r3aktMissions:
          return Promise.resolve(
            wrapped([
              {
                uid: missionUid,
                mission_name: "Wrapped Domain Mission",
                mission_status: "MISSION_ACTIVE"
              }
            ])
          );
        case endpoints.r3aktTeams:
          return Promise.resolve(
            wrapped([
              {
                uid: teamUid,
                mission_uid: missionUid,
                mission_uids: [missionUid],
                team_name: "Wrapped Domain Team"
              }
            ])
          );
        case endpoints.r3aktTeamMembers:
          return Promise.resolve(
            wrapped([
              {
                uid: memberUid,
                team_uid: teamUid,
                callsign: "WRAP-DOMAIN-1",
                rns_identity: "wrapped-domain-rns"
              }
            ])
          );
        case endpoints.r3aktAssets:
          return Promise.resolve(
            wrapped([
              {
                asset_uid: assetUid,
                team_member_uid: memberUid,
                name: "Wrapped Domain Asset",
                asset_type: "SUPPLY"
              }
            ])
          );
        case endpoints.r3aktAssignments:
          return Promise.resolve(
            wrapped([
              {
                assignment_uid: assignmentUid,
                mission_uid: missionUid,
                task_uid: "task-wrapped-domain",
                team_member_rns_identity: "wrapped-domain-rns",
                assets: [assetUid]
              }
            ])
          );
        case endpoints.checklists:
          return Promise.resolve({ checklists: [] });
        case endpoints.checklistTemplates:
          return Promise.resolve({ templates: [] });
        case endpoints.topics:
        case endpoints.r3aktEvents:
        case endpoints.r3aktMissionChanges:
        case endpoints.r3aktLogEntries:
        case endpoints.zones:
        case endpoints.r3aktSkills:
        case endpoints.r3aktTeamMemberSkills:
        case endpoints.r3aktTaskSkillRequirements:
          return Promise.resolve(wrapped([]));
        default:
          return Promise.reject(new Error(`Unexpected GET ${path}`));
      }
    });
  });

  it("loads wrapped mission domain collection responses", async () => {
    const store = useMissionWorkspaceStore();

    await store.loadWorkspace();
    store.setSelectedMissionUid(missionUid);

    expect(store.missions).toHaveLength(1);
    expect(store.missionScopedMembers).toHaveLength(1);
    expect(store.missionScopedAssets).toHaveLength(1);
    expect(store.missionScopedAssignments).toHaveLength(1);
    expect(store.missionScopedAssets[0]?.asset_uid).toBe(assetUid);
    expect(store.missionScopedAssignments[0]?.assignment_uid).toBe(assignmentUid);
  });
});
