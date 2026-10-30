import { afterEach, describe, expect, it, vi } from "vitest";
import { createApp, nextTick, type App } from "vue";
import { shareMarker } from "../src/api/marker-share";
import MarkerShareModal from "../src/components/MarkerShareModal.vue";
const { post } = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock("../src/api/client", () => ({ post }));
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
    app = createApp(MarkerShareModal, { markerId: "marker", markerName: "Ridge" }); app.mount(root);
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
});
