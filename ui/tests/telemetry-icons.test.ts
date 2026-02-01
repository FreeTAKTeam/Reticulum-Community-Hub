import { describe } from "vitest";
import { expect } from "vitest";
import { it } from "vitest";
import { resolveTelemetryIconKey } from "../src/utils/telemetry-icons";

describe("telemetry icon mapping", () => {
  it("maps telemetry_type to a known icon key", () => {
    const entry = { data: { telemetry_type: "vehicle" } } as any;
    expect(resolveTelemetryIconKey(entry)).toBe("vehicle");
  });

  it("normalizes aliases to canonical keys", () => {
    const entry = { data: { symbol: "Group / Community" } } as any;
    expect(resolveTelemetryIconKey(entry)).toBe("group");
    const vehicleSensor = { data: { symbol: "Vehicle Sensor" } } as any;
    expect(resolveTelemetryIconKey(vehicleSensor)).toBe("sensor");
  });

  it("falls back to marker when no hint is present", () => {
    const entry = { data: {} } as any;
    expect(resolveTelemetryIconKey(entry)).toBe("marker");
  });
});
