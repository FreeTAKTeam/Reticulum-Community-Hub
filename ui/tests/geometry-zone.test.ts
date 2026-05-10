import { describe, expect, it } from "vitest";
import {
  closePolygonRing,
  formatAreaLabel,
  normalizePolygonPoints,
  polygonAreaSquareMeters,
  polygonCentroid,
  polygonMidpoints,
} from "../src/utils/geometry";

describe("zone geometry utilities", () => {
  const square = [
    { lat: 0, lon: 0 },
    { lat: 0, lon: 0.01 },
    { lat: 0.01, lon: 0.01 },
    { lat: 0.01, lon: 0 },
  ];

  it("normalizes polygon ring points", () => {
    const normalized = normalizePolygonPoints([...square, square[0]]);
    expect(normalized).toHaveLength(4);
    const closed = closePolygonRing(normalized);
    expect(closed).toHaveLength(5);
    expect(closed[0].lat).toBe(closed[closed.length - 1].lat);
    expect(closed[0].lon).toBe(closed[closed.length - 1].lon);
  });

  it("computes polygon area and centroid", () => {
    const area = polygonAreaSquareMeters(square);
    expect(area).toBeGreaterThan(1_200_000);
    expect(area).toBeLessThan(1_300_000);

    const centroid = polygonCentroid(square);
    expect(centroid).not.toBeNull();
    expect(centroid?.lat).toBeCloseTo(0.005, 3);
    expect(centroid?.lon).toBeCloseTo(0.005, 3);
  });

  it("computes edge midpoints and formats area labels", () => {
    const midpoints = polygonMidpoints(square);
    expect(midpoints).toHaveLength(4);
    const label = formatAreaLabel(1_250_000);
    expect(label).toContain("km²");
    expect(label).toContain("mi²");
  });
});
