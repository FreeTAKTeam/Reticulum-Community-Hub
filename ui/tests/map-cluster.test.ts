import { describe, expect, it } from "vitest";
import { ICON_PIXEL_RATIO, ICON_RASTER_SIZE, resolveClusterRadius, resolveIconSize } from "../src/utils/map-cluster";

describe("map cluster utilities", () => {
  it("keeps marker icons within a standard 18-30 px range at every zoom", () => {
    const basePx = ICON_RASTER_SIZE / ICON_PIXEL_RATIO;
    expect(basePx).toBe(24);
    expect(resolveIconSize(0) * basePx).toBeCloseTo(18, 6);
    expect(resolveIconSize(3) * basePx).toBeCloseTo(18, 6);
    expect(resolveIconSize(9) * basePx).toBeCloseTo(24, 6);
    expect(resolveIconSize(15) * basePx).toBeCloseTo(30, 6);
    expect(resolveIconSize(22) * basePx).toBeCloseTo(30, 6);
  });

  it("returns cluster radius buckets for zoom tiers", () => {
    expect(resolveClusterRadius(1)).toBe(220);
    expect(resolveClusterRadius(3)).toBe(220);
    expect(resolveClusterRadius(3.5)).toBe(180);
    expect(resolveClusterRadius(5)).toBe(140);
    expect(resolveClusterRadius(7)).toBe(110);
    expect(resolveClusterRadius(9)).toBe(80);
    expect(resolveClusterRadius(10.5)).toBe(55);
    expect(resolveClusterRadius(12)).toBe(35);
  });
});
