import { beforeEach, describe, expect, it, vi } from "vitest";
import { createApp, nextTick } from "vue";
import FirstRunSetupWizard from "./FirstRunSetupWizard.vue";
import { completeSetup, fetchSetupStatus } from "../api/setup";
import { DEFAULT_TCP_COMMUNITY_SERVER } from "../utils/tcp-community-servers";

vi.mock("../api/setup", () => ({
  fetchSetupStatus: vi.fn().mockResolvedValue({ setup_required: true }),
  completeSetup: vi.fn()
}));

describe("first-run password feedback", () => {
  beforeEach(() => {
    vi.mocked(fetchSetupStatus).mockResolvedValue({
      setup_required: true, pin_enrolled: false, remote_password_configured: false
    });
    vi.mocked(completeSetup).mockReset();
  });

  it("rejects four emoji and accepts eight Unicode characters", async () => {
    const host = document.createElement("div");
    document.body.appendChild(host);
    const app = createApp(FirstRunSetupWizard);
    app.mount(host);
    const dialog = document.querySelector<HTMLElement>('[role="dialog"]');
    if (!dialog) {
      throw new Error("Setup dialog did not mount");
    }
    try {
      const submit = async () => {
        dialog.querySelector("form")?.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
        await nextTick();
      };
      await submit();
      await submit();
      const setPassword = async (value: string) => {
        const inputs = dialog.querySelectorAll<HTMLInputElement>('input[type="password"]');
        expect(inputs.length).toBe(2);
        for (const input of inputs) {
          input.value = value;
          input.dispatchEvent(new Event("input", { bubbles: true }));
        }
        await nextTick();
      };
      await setPassword("😀😀😀😀");
      await submit();
      expect(dialog.textContent).toContain("Use at least eight characters.");
      expect(dialog.querySelectorAll('input[type="password"]').length).toBe(2);
      await setPassword("😀😀😀😀😀😀😀😀");
      await submit();
      expect(dialog.textContent).toContain("Kill switch PIN");
      expect(dialog.textContent).not.toContain("Use at least eight characters.");
    } finally {
      app.unmount();
      host.remove();
    }
  });

  it.each(["toml", "ini", undefined] as const)("submits the daemon config format advertised by setup status: %s", async (format) => {
    vi.mocked(fetchSetupStatus).mockResolvedValue({
      setup_required: true, pin_enrolled: false, remote_password_configured: false,
      ...(format ? { reticulum_config_format: format } : {})
    });
    const host = document.createElement("div");
    document.body.appendChild(host);
    const app = createApp(FirstRunSetupWizard);
    app.mount(host);
    await nextTick();
    const dialog = document.querySelector<HTMLElement>('[role="dialog"]');
    if (!dialog) { throw new Error("Setup dialog did not mount"); }
    try {
      const submit = async () => {
        dialog.querySelector("form")?.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
        await nextTick();
      };
      const setPasswords = async (value: string) => {
        for (const input of dialog.querySelectorAll<HTMLInputElement>('input[type="password"]')) {
          input.value = value;
          input.dispatchEvent(new Event("input", { bubbles: true }));
        }
        await nextTick();
      };
      await submit();
      const custom = dialog.querySelector<HTMLInputElement>('input[type="text"]');
      if (!custom) { throw new Error("Custom TCP endpoint input did not mount"); }
      custom.value = 'peer"\\host:4242';
      custom.dispatchEvent(new Event("input", { bubbles: true }));
      await nextTick();
      const add = Array.from(dialog.querySelectorAll("button")).find((button) => button.textContent?.trim() === "Add");
      if (!add) { throw new Error("Add endpoint button did not mount"); }
      add.click();
      await nextTick();
      await submit();
      await setPasswords("password-for-test");
      await submit();
      await setPasswords("123456");
      await submit();

      expect(completeSetup).toHaveBeenCalledTimes(1);
      const content = vi.mocked(completeSetup).mock.calls[0][0].reticulum_config_text ?? "";
      const server = DEFAULT_TCP_COMMUNITY_SERVER;
      if (format === "toml") {
        expect(content).toBe([
          "[reticulum]", "enable_transport = true", "share_instance = true", "",
          "[[interfaces]]", `name = ${JSON.stringify(server.name)}`, 'type = "tcp_client"',
          "enabled = true", `host = ${JSON.stringify(server.host)}`, `port = ${server.port}`, "",
          "[[interfaces]]", `name = ${JSON.stringify('TCP peer"\\host:4242')}`, 'type = "tcp_client"',
          "enabled = true", `host = ${JSON.stringify('peer"\\host')}`, "port = 4242", ""
        ].join("\n"));
      } else {
        expect(content).toContain("enable_transport = yes");
        expect(content).toContain("share_instance = yes");
        expect(content).toContain("type = TCPClientInterface");
        expect(content).toContain(`target_host = ${server.host}`);
        expect(content).toContain(`target_port = ${server.port}`);
        expect(content).not.toContain("[[interfaces]]");
      }
    } finally {
      app.unmount();
      host.remove();
    }
  });
});
