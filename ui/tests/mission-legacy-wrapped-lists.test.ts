import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { createMemoryHistory, createRouter } from "vue-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import MissionsLegacyPage from "../src/pages/missions/MissionsLegacyPage.vue";

const { getMock, postMock } = vi.hoisted(() => ({
  getMock: vi.fn(),
  postMock: vi.fn()
}));

vi.mock("../src/api/client", () => ({
  get: getMock,
  post: postMock,
  put: vi.fn(),
  patch: vi.fn(),
  del: vi.fn()
}));

type MountedPage = {
  unmount: () => void;
};

const missionUid = "mission-wrapped";
const teamUid = "team-wrapped";
const memberUid = "member-wrapped";

const waitForUi = async () => {
  await nextTick();
  await new Promise((resolve) => window.setTimeout(resolve, 0));
  await nextTick();
};

const text = () => document.body.textContent ?? "";

const clickButton = async (label: string) => {
  const button = Array.from(document.querySelectorAll("button")).find((entry) =>
    (entry.textContent ?? "").includes(label)
  );
  if (!(button instanceof HTMLButtonElement)) {
    throw new Error(`Button not found: ${label}`);
  }
  button.click();
  await waitForUi();
};

const mountPage = async (): Promise<MountedPage> => {
  const root = document.createElement("div");
  document.body.append(root);
  const pinia = createPinia();
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: "/missions", component: MissionsLegacyPage }]
  });
  await router.push(`/missions?mission_uid=${missionUid}&screen=missionTeamMembers`);
  await router.isReady();
  setActivePinia(pinia);
  const app = createApp(MissionsLegacyPage);
  app.use(pinia);
  app.use(router);
  app.mount(root);
  await waitForUi();
  await waitForUi();
  return {
    unmount: () => {
      app.unmount();
      root.remove();
    }
  };
};

describe("legacy mission workspace wrapped lists", () => {
  let mounted: MountedPage | null = null;

  beforeEach(() => {
    document.body.innerHTML = "";
    getMock.mockReset();
    postMock.mockReset();
    getMock.mockImplementation((path: string) => {
      switch (path) {
        case "/api/r3akt/missions":
          return Promise.resolve({
            value: [
              {
                uid: missionUid,
                mission_name: "Wrapped Mission",
                mission_status: "MISSION_ACTIVE"
              }
            ],
            Count: 1
          });
        case "/api/r3akt/teams":
          return Promise.resolve({
            value: [
              {
                uid: teamUid,
                team_name: "Wrapped Team",
                team_description: "Wrapped response team",
                mission_uid: missionUid,
                mission_uids: [missionUid]
              }
            ],
            Count: 1
          });
        case "/api/r3akt/team-members":
          return Promise.resolve({
            value: [
              {
                uid: memberUid,
                team_uid: teamUid,
                display_name: "Wrapped Member",
                callsign: "WRAP-1",
                rns_identity: "wrapped-member-rns",
                role: "TEAM_LEAD",
                availability: "AVAILABLE"
              }
            ],
            Count: 1
          });
        case "/api/EmergencyActionMessage":
          return Promise.resolve({
            value: [
              {
                callsign: "WRAP-1",
                subject_type: "member",
                team_member_uid: memberUid,
                team_uid: teamUid,
                security_status: "Green",
                capability_status: "Unknown",
                preparedness_status: "Unknown",
                medical_status: "Unknown",
                mobility_status: "Unknown",
                comms_status: "Unknown"
              }
            ],
            Count: 1
          });
        case "/Topic":
        case "/api/r3akt/assets":
        case "/api/r3akt/assignments":
        case "/api/r3akt/events?limit=25&include_payload=false":
        case "/api/r3akt/mission-changes?include_delta=false":
        case "/api/r3akt/log-entries":
        case "/api/zones":
        case "/api/r3akt/skills":
        case "/api/r3akt/team-member-skills":
        case "/api/r3akt/task-skill-requirements":
          return Promise.resolve({ value: [], Count: 0 });
        case "/checklists":
          return Promise.resolve({ checklists: [] });
        case "/checklists/templates":
          return Promise.resolve({ templates: [] });
        default:
          return Promise.reject(new Error(`Unexpected GET ${path}`));
      }
    });
  });

  afterEach(() => {
    mounted?.unmount();
    mounted = null;
    vi.restoreAllMocks();
  });

  it("renders mission team member status cards from wrapped API list responses", async () => {
    mounted = await mountPage();

    expect(text()).toContain("Total Missions");
    expect(text()).toContain("1");
    expect(text()).toContain("Wrapped Mission");

    await clickButton("Team");

    expect(text()).toContain("Wrapped Team");
    expect(text()).toContain("WRAP-1");
    expect(text()).toContain("Member Status Board");
  });
});
