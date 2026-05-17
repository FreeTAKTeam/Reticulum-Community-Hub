import { describe, expect, it } from "vitest";

import { encodeMecpLogContent } from "./mecp-compose";

describe("encodeMecpLogContent", () => {
  it("builds a compact MECP body from severity, event code, and details", () => {
    expect(
      encodeMecpLogContent({
        severity: "1",
        eventCode: "S01",
        details: "  Poco  "
      })
    ).toBe("MECP/1/S01 Poco");
  });

  it("omits blank details while preserving the MECP envelope", () => {
    expect(
      encodeMecpLogContent({
        severity: "2",
        eventCode: "W05",
        details: "   "
      })
    ).toBe("MECP/2/W05");
  });
});
