import { createApp, h, nextTick } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import MissionOverviewScreen from "../src/pages/missions/MissionOverviewScreen.vue";
import { useAuditExportActions } from "../src/composables/missions/useAuditExportActions";

const { getMock } = vi.hoisted(() => ({
  getMock: vi.fn()
}));

vi.mock("../src/api/client", () => ({
  get: getMock
}));

type MountedComponent = {
  root: HTMLElement;
  unmount: () => void;
};

const defaultOverviewProps = {
  missionStatus: "MISSION_ACTIVE",
  checklistRuns: 1,
  openTasks: 2,
  teamMembers: 3,
  assignedAssets: 4,
  assignedZones: 5,
  missionUid: "mission-alpha",
  missionTopicName: "Alpha Topic",
  missionDescription: "Alpha description",
  missionTotalTasks: 6,
  boardCounts: {
    pending: 1,
    late: 1,
    complete: 1
  },
  boardLaneTasks: {
    pending: [{ id: "task-pending", name: "Pending task", meta: "Tactical" }],
    late: [{ id: "task-late", name: "Late task", meta: "Medical" }],
    complete: [{ id: "task-complete", name: "Complete task", meta: "Logistics" }]
  },
  missionAudit: [
    {
      uid: "audit-event-1",
      timestamp: "2026-06-23T06:30:00Z",
      type: "Domain Event",
      message: "Mission updated",
      details: {
        source: "domain_event",
        event_uid: "event-1",
        payload: {
          mission_uid: "mission-alpha",
          status: "MISSION_ACTIVE"
        }
      }
    },
    {
      uid: "audit-event-empty",
      timestamp: "2026-06-23T06:31:00Z",
      type: "Log Entry",
      message: "Empty detail row",
      details: {}
    }
  ]
};

const text = () => document.body.textContent ?? "";

const mountOverview = (onRequestAction = vi.fn()): MountedComponent => {
  const root = document.createElement("div");
  document.body.append(root);
  const app = createApp({
    render: () =>
      h(MissionOverviewScreen, {
        ...defaultOverviewProps,
        onRequestAction
      })
  });
  app.mount(root);
  return {
    root,
    unmount: () => {
      app.unmount();
      root.remove();
    }
  };
};

const clickButton = async (label: string, index = 0) => {
  const matches = Array.from(document.querySelectorAll("button")).filter((button) =>
    (button.textContent ?? "").includes(label)
  );
  const button = matches[index];
  if (!(button instanceof HTMLButtonElement)) {
    throw new Error(`Button not found: ${label}`);
  }
  button.click();
  await nextTick();
  return button;
};

type CapturedBlob = {
  text: () => Promise<string>;
  type?: string;
};

const blobText = async (blob: CapturedBlob | null) => {
  if (!blob) {
    return "";
  }
  return blob.text();
};

describe("mission audit overview", () => {
  let mounted: MountedComponent | null = null;

  beforeEach(() => {
    document.body.innerHTML = "";
    getMock.mockReset();
  });

  afterEach(() => {
    mounted?.unmount();
    mounted = null;
    vi.restoreAllMocks();
  });

  it("expands and hides mission audit details from the rendered table", async () => {
    mounted = mountOverview();

    expect(text()).toContain("Mission Activity / Audit");
    expect(text()).toContain("Mission updated");
    expect(text()).not.toContain("domain_event");

    await clickButton("Details");

    expect(text()).toContain("domain_event");
    expect(text()).toContain("MISSION_ACTIVE");

    await clickButton("Hide");

    expect(text()).not.toContain("domain_event");

    const disabledDetails = await clickButton("Details", 1);
    expect(disabledDetails.disabled).toBe(true);
  });

  it("emits the export-log action from the visible audit control", async () => {
    const onRequestAction = vi.fn();
    mounted = mountOverview(onRequestAction);

    await clickButton("Export Log");

    expect(onRequestAction).toHaveBeenCalledWith("Export Log");
  });
});

describe("audit export actions", () => {
  let createdBlob: CapturedBlob | null = null;
  let clickedAnchor: HTMLAnchorElement | null = null;

  beforeEach(() => {
    document.body.innerHTML = "";
    getMock.mockReset();
    createdBlob = null;
    clickedAnchor = null;
    vi.stubGlobal(
      "Blob",
      class MockBlob {
        readonly parts: unknown[];
        readonly type: string;

        constructor(parts: unknown[], options?: { type?: string }) {
          this.parts = parts;
          this.type = options?.type ?? "";
        }

        text() {
          return Promise.resolve(this.parts.map((part) => String(part)).join(""));
        }
      }
    );
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn()
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn()
    });
    vi.spyOn(URL, "createObjectURL").mockImplementation((blob) => {
      createdBlob = blob as CapturedBlob;
      return "blob:mission-audit";
    });
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
    vi.spyOn(document.body, "append").mockImplementation((node) => {
      if (node instanceof HTMLAnchorElement) {
        clickedAnchor = node;
      }
    });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("downloads mission audit JSON with the selected mission UID", async () => {
    const { exportMissionAudit } = useAuditExportActions();

    exportMissionAudit("mission-alpha", [{ uid: "event-1", message: "Mission updated" }]);

    expect(clickedAnchor?.download).toBe("mission-audit-mission-alpha.json");
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:mission-audit");
    await expect(blobText(createdBlob)).resolves.toContain('"uid": "event-1"');
  });

  it("filters mission snapshots before downloading them", async () => {
    getMock.mockResolvedValue([
      { aggregate_uid: "mission-alpha", state: { value: "kept" } },
      { aggregate_uid: "mission-bravo", state: { value: "excluded" } }
    ]);
    const { exportSnapshots } = useAuditExportActions();

    await exportSnapshots("mission-alpha");

    expect(getMock).toHaveBeenCalledWith("/api/r3akt/snapshots");
    expect(clickedAnchor?.download).toBe("mission-snapshots-mission-alpha.json");
    const payload = await blobText(createdBlob);
    expect(payload).toContain('"value": "kept"');
    expect(payload).not.toContain("excluded");
  });
});
