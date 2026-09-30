import { describe, expect, it, vi } from "vitest";
import { createApp, nextTick } from "vue";
import FirstRunSetupWizard from "./FirstRunSetupWizard.vue";

vi.mock("../api/setup", () => ({
  fetchSetupStatus: vi.fn().mockResolvedValue({ setup_required: true }),
  completeSetup: vi.fn()
}));

describe("first-run password feedback", () => {
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
});
