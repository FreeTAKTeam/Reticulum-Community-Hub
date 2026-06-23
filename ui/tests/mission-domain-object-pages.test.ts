import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick, type Component } from "vue";
import { createMemoryHistory, createRouter } from "vue-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AssetObjectLegacyPage from "../src/pages/missions/domains/AssetObjectLegacyPage.vue";
import LogEntryObjectLegacyPage from "../src/pages/missions/domains/LogEntryObjectLegacyPage.vue";

const { delMock, getMock, postMock } = vi.hoisted(() => ({
  delMock: vi.fn(),
  getMock: vi.fn(),
  postMock: vi.fn()
}));

vi.mock("../src/api/client", () => ({
  del: delMock,
  get: getMock,
  post: postMock
}));

type MountedPage = {
  root: HTMLElement;
  unmount: () => void;
};

const missionAlpha = {
  uid: "mission-alpha",
  mission_name: "Alpha Mission",
  mission_status: "MISSION_ACTIVE"
};

const teamAlpha = {
  uid: "team-alpha",
  mission_uid: "mission-alpha",
  team_name: "Alpha Team"
};

const memberAlpha = {
  uid: "member-alpha",
  team_uid: "team-alpha",
  display_name: "Alpha Member",
  callsign: "ALPHA-1",
  rns_identity: "member-alpha-rns"
};

const assetAlpha = {
  asset_uid: "asset-alpha",
  team_member_uid: "member-alpha",
  name: "Alpha Pack",
  asset_type: "FIELD_UNIT",
  serial_number: "SN-ALPHA",
  status: "AVAILABLE",
  location: "Cache One",
  notes: "Ready",
  created_at: "2026-06-23T06:00:00Z",
  updated_at: "2026-06-23T06:00:00Z"
};

const logAlpha = {
  entry_uid: "log-alpha",
  mission_uid: "mission-alpha",
  callsign: "ALPHA-1",
  content: "Initial log entry",
  server_time: "2026-06-23T06:10:00Z",
  client_time: "2026-06-23T06:09:00Z",
  keywords: ["ops", "initial"]
};

const text = () => document.body.textContent ?? "";

const waitForUi = async () => {
  await nextTick();
  await new Promise((resolve) => window.setTimeout(resolve, 0));
  await nextTick();
};

const byButtonText = (label: string, index = 0) => {
  const matches = Array.from(document.querySelectorAll("button")).filter((entry) =>
    (entry.textContent ?? "").includes(label)
  );
  const button = matches[index];
  if (!(button instanceof HTMLButtonElement)) {
    throw new Error(`Button not found: ${label}`);
  }
  return button;
};

const fieldControlByLabel = (label: string) => {
  const labelNode = Array.from(document.querySelectorAll("label")).find((entry) =>
    (entry.textContent ?? "").includes(label)
  );
  if (!(labelNode instanceof HTMLLabelElement)) {
    throw new Error(`Label not found: ${label}`);
  }
  return labelNode;
};

const selectByLabel = (label: string) => {
  const select = fieldControlByLabel(label).closest(".cui-field")?.querySelector("select");
  if (!(select instanceof HTMLSelectElement)) {
    throw new Error(`Select not found for label: ${label}`);
  }
  return select;
};

const inputByLabel = (label: string) => {
  const field = fieldControlByLabel(label);
  const control = field.querySelector("input, textarea");
  if (!(control instanceof HTMLInputElement) && !(control instanceof HTMLTextAreaElement)) {
    throw new Error(`Input not found for label: ${label}`);
  }
  return control;
};

const clickButton = async (label: string, index = 0) => {
  byButtonText(label, index).click();
  await waitForUi();
};

const fillField = async (label: string, value: string) => {
  const input = inputByLabel(label);
  input.value = value;
  input.dispatchEvent(new Event("input", { bubbles: true }));
  await waitForUi();
};

const selectOption = async (label: string, value: string) => {
  const select = selectByLabel(label);
  select.value = value;
  select.dispatchEvent(new Event("change", { bubbles: true }));
  await waitForUi();
};

const mountPage = async (component: Component, path: string): Promise<MountedPage> => {
  const root = document.createElement("div");
  document.body.appendChild(root);
  const pinia = createPinia();
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: path.split("?")[0] ?? path, component }]
  });
  await router.push(path);
  await router.isReady();
  setActivePinia(pinia);
  const app = createApp(component);
  app.use(pinia);
  app.use(router);
  app.mount(root);
  await waitForUi();
  return {
    root,
    unmount: () => {
      app.unmount();
      root.remove();
    }
  };
};

const setupAssetApiMocks = () => {
  getMock.mockImplementation((path: string) => {
    if (path === "/api/r3akt/missions") return Promise.resolve([missionAlpha]);
    if (path === "/api/r3akt/teams") return Promise.resolve([teamAlpha]);
    if (path === "/api/r3akt/team-members") return Promise.resolve([memberAlpha]);
    if (path === "/api/r3akt/assets") return Promise.resolve([assetAlpha]);
    if (path === "/api/r3akt/assignments") return Promise.resolve([]);
    return Promise.reject(new Error(`Unexpected GET ${path}`));
  });
  postMock.mockResolvedValue(assetAlpha);
  delMock.mockResolvedValue(undefined);
};

const setupLogApiMocks = () => {
  getMock.mockImplementation((path: string) => {
    if (path === "/api/r3akt/missions") return Promise.resolve([missionAlpha]);
    if (path === "/api/r3akt/log-entries?mission_uid=mission-alpha") return Promise.resolve([logAlpha]);
    if (path === "/api/r3akt/log-entries") return Promise.resolve([logAlpha]);
    return Promise.reject(new Error(`Unexpected GET ${path}`));
  });
  postMock.mockResolvedValue(logAlpha);
};

describe("mission domain object pages", () => {
  let page: MountedPage | null = null;
  let confirmMock: ReturnType<typeof vi.fn>;
  let clipboardWriteTextMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    document.body.innerHTML = "";
    delMock.mockReset();
    getMock.mockReset();
    postMock.mockReset();
    confirmMock = vi.fn(() => true);
    clipboardWriteTextMock = vi.fn(() => Promise.resolve());
    vi.stubGlobal("confirm", confirmMock);
    vi.stubGlobal("navigator", {
      clipboard: {
        writeText: clipboardWriteTextMock
      }
    });
  });

  afterEach(() => {
    page?.unmount();
    page = null;
    vi.unstubAllGlobals();
  });

  it("drives mission asset create, edit, and delete actions from visible controls", async () => {
    setupAssetApiMocks();
    page = await mountPage(AssetObjectLegacyPage, "/missions/assets?mission_uid=mission-alpha");

    expect(text()).toContain("Alpha Pack");
    expect(text()).toContain("ALPHA-1");

    await clickButton("New Asset");
    await fillField("Name", "Water Filter");
    await fillField("Asset Type", "SUPPLY");
    await selectOption("Team Member", "member-alpha");
    await fillField("Serial Number", "SN-WATER");
    await fillField("Location", "Cache Two");
    await fillField("Notes", "Ready for field pickup");
    await clickButton("Create Asset");

    expect(postMock).toHaveBeenCalledWith(
      "/api/r3akt/assets",
      expect.objectContaining({
        name: "Water Filter",
        asset_type: "SUPPLY",
        team_member_uid: "member-alpha",
        serial_number: "SN-WATER",
        location: "Cache Two",
        notes: "Ready for field pickup"
      }),
      { timeoutMs: 30000 }
    );

    await clickButton("Edit");
    await fillField("Name", "Alpha Pack Updated");
    await clickButton("Save Asset");

    expect(postMock).toHaveBeenCalledWith(
      "/api/r3akt/assets",
      expect.objectContaining({
        asset_uid: "asset-alpha",
        name: "Alpha Pack Updated"
      }),
      { timeoutMs: 30000 }
    );

    confirmMock.mockReturnValueOnce(false).mockReturnValueOnce(true);
    await clickButton("Delete");

    expect(delMock).not.toHaveBeenCalled();

    await clickButton("Delete");

    expect(confirmMock).toHaveBeenCalledWith('Delete asset "Alpha Pack"?');
    expect(delMock).toHaveBeenCalledWith("/api/r3akt/assets/asset-alpha", { timeoutMs: 30000 });
  });

  it("drives mission log write, copy, and edit actions from visible controls", async () => {
    setupLogApiMocks();
    page = await mountPage(LogEntryObjectLegacyPage, "/missions/logs?mission_uid=mission-alpha");

    expect(text()).toContain("Initial log entry");
    expect(text()).toContain("Alpha Mission");

    await fillField("Author Callsign", "EAGLE-1");
    await fillField("Keywords", "ops, green");
    await fillField("Text", "Status green");
    await clickButton("Write Entry");

    expect(postMock).toHaveBeenCalledWith(
      "/api/r3akt/log-entries",
      expect.objectContaining({
        mission_uid: "mission-alpha",
        callsign: "EAGLE-1",
        content: "Status green",
        keywords: ["ops", "green"]
      }),
      { timeoutMs: 30000 }
    );

    await clickButton("Copy");

    expect(clipboardWriteTextMock).toHaveBeenCalledWith(expect.stringContaining('"entry_uid": "log-alpha"'));

    await clickButton("Edit");
    await fillField("Text", "Updated status log");
    await clickButton("Update Entry");

    expect(postMock).toHaveBeenCalledWith(
      "/api/r3akt/log-entries",
      expect.objectContaining({
        entry_uid: "log-alpha",
        mission_uid: "mission-alpha",
        content: "Updated status log"
      }),
      { timeoutMs: 30000 }
    );
  });
});
