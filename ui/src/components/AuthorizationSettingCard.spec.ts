import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createApp, nextTick } from "vue";
import { createPinia } from "pinia";
import { createMemoryHistory, createRouter } from "vue-router";
import AuthorizationSettingCard from "./AuthorizationSettingCard.vue";
import {
  decodeAuthorizationSetting,
  fetchAuthorizationSetting,
  saveAuthorizationSetting
} from "../api/authorization-setting";

vi.mock("../api/authorization-setting", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/authorization-setting")>();
  return {
    ...actual,
    fetchAuthorizationSetting: vi.fn(),
    saveAuthorizationSetting: vi.fn()
  };
});

const flush = async () => {
  for (let index = 0; index < 4; index += 1) {
    await Promise.resolve();
    await nextTick();
  }
};

const mountCard = async () => {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/", component: { template: "<div />" } },
      { path: "/users", component: { template: "<div />" } }
    ]
  });
  const app = createApp(AuthorizationSettingCard);
  app.use(createPinia());
  app.use(router);
  app.mount(host);
  await flush();
  const unmount = () => {
    app.unmount();
    host.remove();
  };
  const toggle = () => host.querySelector<HTMLInputElement>('input[type="checkbox"]');
  return { host, unmount, toggle };
};

const changeTo = async (input: HTMLInputElement, checked: boolean) => {
  input.checked = checked;
  input.dispatchEvent(new Event("change", { bubbles: true }));
  await flush();
};

const confirmButton = () =>
  Array.from(document.querySelectorAll<HTMLButtonElement>('[role="dialog"] button')).find(
    (button) => button.textContent?.trim() === "Require authorization"
  );

describe("decodeAuthorizationSetting", () => {
  it("accepts a boolean flag and rejects anything else", () => {
    expect(decodeAuthorizationSetting({ authorization_required: true })).toEqual({ authorization_required: true });
    for (const invalid of [null, {}, { authorization_required: "true" }, []]) {
      expect(() => decodeAuthorizationSetting(invalid)).toThrow();
    }
  });
});

describe("AuthorizationSettingCard", () => {
  let mounted: Awaited<ReturnType<typeof mountCard>> | null = null;

  beforeEach(() => {
    vi.mocked(fetchAuthorizationSetting).mockReset();
    vi.mocked(saveAuthorizationSetting).mockReset();
  });

  afterEach(() => {
    mounted?.unmount();
    mounted = null;
  });

  it("shows the hub's value and asks for confirmation before enabling", async () => {
    vi.mocked(fetchAuthorizationSetting).mockResolvedValue({ authorization_required: false });
    vi.mocked(saveAuthorizationSetting).mockResolvedValue({ authorization_required: true });
    mounted = await mountCard();
    const input = mounted.toggle();
    expect(input?.checked).toBe(false);

    await changeTo(input!, true);
    expect(saveAuthorizationSetting).not.toHaveBeenCalled();
    expect(input!.checked).toBe(false);

    confirmButton()?.click();
    await flush();
    expect(saveAuthorizationSetting).toHaveBeenCalledWith(true);
    expect(mounted.toggle()?.checked).toBe(true);
  });

  it("disables without confirmation and restores the hub value when saving fails", async () => {
    vi.mocked(fetchAuthorizationSetting).mockResolvedValue({ authorization_required: true });
    vi.mocked(saveAuthorizationSetting).mockRejectedValue(new Error("offline"));
    mounted = await mountCard();

    await changeTo(mounted.toggle()!, false);
    expect(saveAuthorizationSetting).toHaveBeenCalledWith(false);
    expect(mounted.toggle()?.checked).toBe(true);
  });

  it("reports a load failure instead of showing the switch as off", async () => {
    vi.mocked(fetchAuthorizationSetting).mockRejectedValue(new Error("Unauthorized"));
    mounted = await mountCard();

    expect(mounted.toggle()).toBeNull();
    expect(mounted.host.textContent).toContain("Unable to load the authorization setting: Unauthorized");
  });
});
