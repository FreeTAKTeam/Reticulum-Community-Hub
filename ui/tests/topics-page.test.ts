import { createPinia, setActivePinia } from "pinia";
import { createApp, nextTick } from "vue";
import { createMemoryHistory, createRouter } from "vue-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import TopicsPage from "../src/pages/TopicsPage.vue";

const { delMock, getMock, patchMock, postMock } = vi.hoisted(() => ({
  delMock: vi.fn(),
  getMock: vi.fn(),
  patchMock: vi.fn(),
  postMock: vi.fn()
}));

vi.mock("../src/api/client", () => ({
  del: delMock,
  get: getMock,
  patch: patchMock,
  post: postMock
}));

type MountedPage = {
  unmount: () => void;
  root: HTMLElement;
};

const topicAlpha = {
  TopicID: "topic-alpha",
  TopicName: "Alpha",
  TopicPath: "ops.alpha",
  TopicDescription: "Alpha topic"
};

const linkedFile = {
  FileID: "file-linked",
  Name: "linked.txt",
  Category: "file",
  TopicID: "topic-alpha"
};

const openFile = {
  FileID: "file-open",
  Name: "open.txt",
  Category: "file",
  TopicID: null
};

const linkedImage = {
  FileID: "image-linked",
  Name: "linked.png",
  Category: "image",
  TopicID: "topic-alpha"
};

const openImage = {
  FileID: "image-open",
  Name: "open.png",
  Category: "image",
  TopicID: null
};

const subscriberAlpha = {
  SubscriberID: "sub-alpha",
  Destination: "dest-alpha",
  TopicID: "topic-alpha",
  RejectTests: 1,
  Metadata: { display_name: "Alpha Source" }
};

const text = () => document.body.textContent ?? "";

const waitForUi = async () => {
  await nextTick();
  await new Promise((resolve) => window.setTimeout(resolve, 0));
  await nextTick();
};

const byButtonText = (label: string) => {
  const button = Array.from(document.querySelectorAll("button")).find((entry) =>
    (entry.textContent ?? "").includes(label)
  );
  if (!button) {
    throw new Error(`Button not found: ${label}`);
  }
  return button as HTMLButtonElement;
};

const byLabelText = (label: string) => {
  const labelNode = Array.from(document.querySelectorAll("label")).find((entry) =>
    (entry.textContent ?? "").includes(label)
  );
  if (!labelNode) {
    throw new Error(`Label not found: ${label}`);
  }
  const select = labelNode.closest(".cui-field")?.querySelector("select");
  if (!(select instanceof HTMLSelectElement)) {
    throw new Error(`Select not found for label: ${label}`);
  }
  return select;
};

const selectOption = async (label: string, value: string) => {
  const select = byLabelText(label);
  select.value = value;
  select.dispatchEvent(new Event("change", { bubbles: true }));
  await waitForUi();
};

const clickButton = async (label: string) => {
  byButtonText(label).click();
  await waitForUi();
};

const mountPage = async (): Promise<MountedPage> => {
  const root = document.createElement("div");
  document.body.appendChild(root);
  const pinia = createPinia();
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: "/topics", component: TopicsPage }]
  });
  await router.push("/topics");
  await router.isReady();
  setActivePinia(pinia);
  const app = createApp(TopicsPage);
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

const setupApiMocks = () => {
  getMock.mockImplementation((path: string) => {
    if (path === "/Topic") {
      return Promise.resolve([topicAlpha]);
    }
    if (path === "/File") {
      return Promise.resolve([linkedFile, openFile]);
    }
    if (path === "/Image") {
      return Promise.resolve([linkedImage, openImage]);
    }
    if (path === "/Subscriber") {
      return Promise.resolve([subscriberAlpha]);
    }
    if (path === "/Client") {
      return Promise.resolve([{ identity: "dest-alpha", display_name: "Alpha Source" }]);
    }
    if (path === "/Identities") {
      return Promise.resolve([{ Identity: "dest-alpha", DisplayName: "Alpha Source" }]);
    }
    if (path === "/api/rem/peers") {
      return Promise.resolve({ effective_connected_mode: false, items: [] });
    }
    return Promise.reject(new Error(`Unexpected GET ${path}`));
  });
  patchMock.mockImplementation((path: string, payload: { TopicID?: string | null }) => {
    if (path === "/File/file-open") {
      return Promise.resolve({ ...openFile, TopicID: payload.TopicID });
    }
    if (path === "/File/file-linked") {
      return Promise.resolve({ ...linkedFile, TopicID: payload.TopicID });
    }
    if (path === "/Image/image-open") {
      return Promise.resolve({ ...openImage, TopicID: payload.TopicID });
    }
    if (path === "/Image/image-linked") {
      return Promise.resolve({ ...linkedImage, TopicID: payload.TopicID });
    }
    return Promise.reject(new Error(`Unexpected PATCH ${path}`));
  });
  delMock.mockResolvedValue(undefined);
};

describe("topics page", () => {
  let page: MountedPage | null = null;
  let confirmMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    document.body.innerHTML = "";
    delMock.mockReset();
    getMock.mockReset();
    patchMock.mockReset();
    postMock.mockReset();
    setupApiMocks();
    confirmMock = vi.fn(() => true);
    vi.stubGlobal("confirm", confirmMock);
  });

  afterEach(() => {
    page?.unmount();
    page = null;
    vi.unstubAllGlobals();
  });

  it("opens topic asset management and links or removes files from visible controls", async () => {
    page = await mountPage();

    expect(text()).toContain("Alpha");
    expect(text()).toContain("linked.txt");

    await clickButton("Manage Assets");

    expect(text()).toContain("Topic Assets: Alpha");
    expect(text()).toContain("Available Files In Asset Library");
    expect(text()).toContain("open.txt");

    await selectOption("Library File", "file-open");
    await clickButton("Attach File");

    expect(patchMock).toHaveBeenCalledWith("/File/file-open", { TopicID: "topic-alpha" });
    expect(text()).toContain("file-open");

    await selectOption("File", "file-linked");
    await clickButton("Remove File");

    expect(patchMock).toHaveBeenCalledWith("/File/file-linked", { TopicID: null });
  });

  it("honors topic delete confirmation before calling the backend", async () => {
    confirmMock.mockReturnValueOnce(false).mockReturnValueOnce(true);
    page = await mountPage();

    await clickButton("Delete");

    expect(delMock).not.toHaveBeenCalled();
    expect(text()).toContain("Alpha");

    await clickButton("Delete");

    expect(confirmMock).toHaveBeenCalledWith("Delete this topic?");
    expect(delMock).toHaveBeenCalledWith("/Topic?id=topic-alpha");
    expect(text()).not.toContain("Alpha topic");
  });

  it("honors subscriber delete confirmation before removing a subscriber", async () => {
    confirmMock.mockReturnValueOnce(false).mockReturnValueOnce(true);
    page = await mountPage();

    await clickButton("Subscribers");
    expect(text()).toContain("Alpha Source");

    await clickButton("Delete");

    expect(delMock).not.toHaveBeenCalled();
    expect(text()).toContain("Alpha Source");

    await clickButton("Delete");

    expect(confirmMock).toHaveBeenCalledWith("Delete this subscriber?");
    expect(delMock).toHaveBeenCalledWith("/Subscriber?id=sub-alpha");
    expect(text()).not.toContain("Alpha Source");
  });
});
