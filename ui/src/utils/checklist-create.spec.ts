import { describe, expect, it } from "vitest";

import { resolveChecklistCreateEndpoint } from "./checklist-create";

describe("resolveChecklistCreateEndpoint", () => {
  it("defaults Excheck creation to the shared online endpoint", () => {
    expect(resolveChecklistCreateEndpoint()).toBe("/checklists");
    expect(resolveChecklistCreateEndpoint(false)).toBe("/checklists");
  });

  it("switches to the explicit offline endpoint for local drafts", () => {
    expect(resolveChecklistCreateEndpoint(true)).toBe("/checklists/offline");
  });
});
