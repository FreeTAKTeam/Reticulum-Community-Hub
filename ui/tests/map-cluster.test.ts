import { describe, expect, it } from "vitest";
import { resolveClusterRadius, resolveZoomScale } from "../src/utils/map-cluster";

describe("map cluster utilities", () => {
  it("scales icon size by 10% per zoom level", () => {
    expect(resolveZoomScale(1)).toBeCloseTo(1, 6);
    expect(resolveZoomScale(2)).toBeCloseTo(1.1, 6);
    expect(resolveZoomScale(0)).toBeCloseTo(1 / 1.1, 6);
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
