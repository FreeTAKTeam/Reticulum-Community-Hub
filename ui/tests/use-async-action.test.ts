import { describe, expect, it } from "vitest";

import { useAsyncAction } from "../src/composables/useAsyncAction";

describe("useAsyncAction", () => {
  it("resets busy and captures result for successful actions", async () => {
    const action = useAsyncAction();
    const resultPromise = action.run(async () => "ok");

    expect(action.busy.value).toBe(true);
    await expect(resultPromise).resolves.toBe("ok");
    expect(action.busy.value).toBe(false);
    expect(action.error.value).toBeNull();
  });

  it("stores error and clears busy for failed actions", async () => {
    const action = useAsyncAction();
    const failure = new Error("boom");

    await expect(action.run(async () => Promise.reject(failure))).rejects.toThrow("boom");
    expect(action.busy.value).toBe(false);
    expect(action.error.value).toBe(failure);
  });
});
