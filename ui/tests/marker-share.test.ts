import { afterEach, describe, expect, it, vi } from "vitest";
import { createPinia } from "pinia";
import { createApp, nextTick, type App } from "vue";
import { shareMarker } from "../src/api/marker-share";
import MarkerShareModal from "../src/components/MarkerShareModal.vue";
const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock("../src/api/client", () => ({ get, post, put: vi.fn() }));
const receipt = { message_id: "queued", marker_id: "marker", destination: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", delivery_state: "broker_pending" };
let app: App | undefined;
afterEach(() => { app?.unmount(); app = undefined; document.body.replaceChildren(); vi.clearAllMocks(); });

describe("explicit marker sharing", () => {
  it("submits only the selected destination and does not retry a send", async () => {
    post.mockResolvedValueOnce(receipt);
    const signal = new AbortController().signal;
    expect(await shareMarker("marker/id", " aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa ", signal)).toBe(receipt);
    expect(post).toHaveBeenCalledWith("/api/markers/marker%2Fid/share",
      { destination: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" }, { retries: 0, signal });
  });
  it("does not treat an invalid server response as queued", async () => {
    post.mockResolvedValueOnce({});
    await expect(shareMarker("marker", receipt.destination)).rejects.toThrow("Check Messages");
  });
  it("sends only after submission, exposes rejection, and prevents duplicate sends", async () => {
    const root = document.createElement("div"); document.body.append(root);
    get.mockResolvedValue([]);
    app = createApp(MarkerShareModal, { markerId: "marker", markerName: "Ridge" }).use(createPinia()); app.mount(root);
    await nextTick();
    expect(post).not.toHaveBeenCalled();
    const input = document.querySelector("input")!;
    input.value = receipt.destination; input.dispatchEvent(new Event("input", { bubbles: true }));
    await nextTick();
    const form = document.querySelector("form")!;
    post.mockRejectedValueOnce(new Error("Destination is not permitted"));
    form.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
    await vi.waitFor(() => expect(document.querySelector("[role=alert]")?.textContent).toContain("not permitted"));
    let complete!: (value: typeof receipt) => void;
    post.mockImplementationOnce(() => new Promise((resolve) => { complete = resolve; }));
    form.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
    form.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
    expect(post).toHaveBeenCalledTimes(2);
    complete(receipt);
    await vi.waitFor(() => expect(document.querySelector("[role=status]")?.textContent).toContain("Marker queued"));
    expect((document.querySelector("button[type=submit]") as HTMLButtonElement).disabled).toBe(true);
  });

  const users = [
    { identity: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", display_name: "Rescue Mobile", is_rem_capable: true },
    { identity: "cccccccccccccccccccccccccccccccc", display_name: "Alpha Sideband" },
    { identity: "not-an-lxmf-address", display_name: "Broken" },
    { identity: "aaaaaaaabbbbbbbbccccccccdddddddd" }
  ];
  const mountWithUsers = async () => {
    get.mockImplementation(async (path: string) => path.startsWith("/Client") ? users : []);
    const root = document.createElement("div"); document.body.append(root);
    app = createApp(MarkerShareModal, { markerId: "marker", markerName: "Ridge" }).use(createPinia()); app.mount(root);
    await vi.waitFor(() => expect(get).toHaveBeenCalled());
    const input = document.querySelector<HTMLInputElement>("input[role=combobox]")!;
    input.dispatchEvent(new Event("focus"));
    await vi.waitFor(() => expect(document.querySelectorAll("[role=option]").length).toBe(3));
    return input;
  };
  const optionLabels = () => [...document.querySelectorAll("[role=option] .recipient-picker__label")].map((node) => node.textContent);
  const type = async (input: HTMLInputElement, text: string) => {
    input.value = text; input.dispatchEvent(new Event("input", { bubbles: true })); await nextTick();
  };
  const submit = () => document.querySelector("form")!.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));

  it("offers the hub's users, sorted and searchable, and sends to the chosen user", async () => {
    post.mockResolvedValueOnce({ ...receipt, destination: users[0].identity });
    const input = await mountWithUsers();
    expect(optionLabels()).toEqual(["Alpha Sideband", "Rescue Mobile", "aaaaaaaa…"]);
    expect(document.querySelector("[role=option]")?.textContent).toContain("LXMF");

    await type(input, "rescue");
    expect(optionLabels()).toEqual(["Rescue Mobile"]);
    await type(input, "cccccccccc");
    expect(optionLabels()).toEqual(["Alpha Sideband"]);
    await type(input, "res");
    (document.querySelector("[role=option]") as HTMLElement).click();
    await nextTick();
    expect(input.value).toBe("Rescue Mobile");
    expect(document.querySelector("[role=listbox]")).toBeNull();

    submit();
    await vi.waitFor(() => expect(post).toHaveBeenCalledWith("/api/markers/marker/share",
      { destination: users[0].identity }, expect.anything()));
  });

  it("picks a user with the keyboard", async () => {
    post.mockResolvedValueOnce(receipt);
    const input = await mountWithUsers();
    input.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown" }));
    input.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown" }));
    input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter" }));
    await nextTick();
    expect(input.value).toBe("Rescue Mobile");
    const sendButton = document.querySelector<HTMLButtonElement>("button[type=submit]")!;
    expect(sendButton.disabled).toBe(false);
  });

  it("keeps the send button disabled until a user or valid address is chosen", async () => {
    const input = await mountWithUsers();
    const sendButton = document.querySelector<HTMLButtonElement>("button[type=submit]")!;
    await type(input, "alpha");
    expect(sendButton.disabled).toBe(true);
    await type(input, "DDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDD");
    expect(sendButton.disabled).toBe(false);
  });
});
