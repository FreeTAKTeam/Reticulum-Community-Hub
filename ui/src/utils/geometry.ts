export type GeoPoint = {
  lat: number;
  lon: number;
};

const EARTH_RADIUS_M = 6371008.8;
const DEG_TO_RAD = Math.PI / 180;
const RAD_TO_DEG = 180 / Math.PI;
const EPSILON = 1e-9;

const pointsEqual = (left: GeoPoint, right: GeoPoint): boolean => {
  return Math.abs(left.lat - right.lat) <= EPSILON && Math.abs(left.lon - right.lon) <= EPSILON;
};

const projectPoint = (point: GeoPoint, lat0Rad: number, lon0Rad: number) => {
  const lat = point.lat * DEG_TO_RAD;
  const lon = point.lon * DEG_TO_RAD;
  return {
    x: EARTH_RADIUS_M * (lon - lon0Rad) * Math.cos(lat0Rad),
    y: EARTH_RADIUS_M * (lat - lat0Rad),
  };
};

const projectionOrigin = (points: GeoPoint[]) => {
  const avgLat = points.reduce((sum, point) => sum + point.lat, 0) / points.length;
  const avgLon = points.reduce((sum, point) => sum + point.lon, 0) / points.length;
  return {
    lat0Rad: avgLat * DEG_TO_RAD,
    lon0Rad: avgLon * DEG_TO_RAD,
  };
};

export const normalizePolygonPoints = (points: GeoPoint[]): GeoPoint[] => {
  const normalized = points
    .filter((point) => Number.isFinite(point.lat) && Number.isFinite(point.lon))
    .map((point) => ({ lat: point.lat, lon: point.lon }));
  if (normalized.length >= 2 && pointsEqual(normalized[0], normalized[normalized.length - 1])) {
    return normalized.slice(0, -1);
  }
  return normalized;
};

export const closePolygonRing = (points: GeoPoint[]): GeoPoint[] => {
  const normalized = normalizePolygonPoints(points);
  if (!normalized.length) {
    return [];
  }
  if (normalized.length === 1) {
    return [normalized[0], normalized[0]];
  }
  if (pointsEqual(normalized[0], normalized[normalized.length - 1])) {
    return normalized;
  }
  return [...normalized, normalized[0]];
};

export const polygonAreaSquareMeters = (points: GeoPoint[]): number => {
  const normalized = normalizePolygonPoints(points);
  if (normalized.length < 3) {
    return 0;
  }
  const { lat0Rad, lon0Rad } = projectionOrigin(normalized);
  const ring = closePolygonRing(normalized).map((point) => projectPoint(point, lat0Rad, lon0Rad));
  let twiceArea = 0;
  for (let i = 0; i < ring.length - 1; i += 1) {
    twiceArea += ring[i].x * ring[i + 1].y - ring[i + 1].x * ring[i].y;
  }
  return Math.abs(twiceArea) / 2;
};

export const polygonCentroid = (points: GeoPoint[]): GeoPoint | null => {
  const normalized = normalizePolygonPoints(points);
  if (normalized.length < 3) {
    return null;
  }
  const { lat0Rad, lon0Rad } = projectionOrigin(normalized);
  const ring = closePolygonRing(normalized).map((point) => projectPoint(point, lat0Rad, lon0Rad));
  let twiceArea = 0;
  let centroidX = 0;
  let centroidY = 0;

  for (let i = 0; i < ring.length - 1; i += 1) {
    const cross = ring[i].x * ring[i + 1].y - ring[i + 1].x * ring[i].y;
    twiceArea += cross;
    centroidX += (ring[i].x + ring[i + 1].x) * cross;
    centroidY += (ring[i].y + ring[i + 1].y) * cross;
  }

  if (Math.abs(twiceArea) <= EPSILON) {
    const avgLat = normalized.reduce((sum, point) => sum + point.lat, 0) / normalized.length;
    const avgLon = normalized.reduce((sum, point) => sum + point.lon, 0) / normalized.length;
    return { lat: avgLat, lon: avgLon };
  }

  const x = centroidX / (3 * twiceArea);
  const y = centroidY / (3 * twiceArea);
  const lat = (y / EARTH_RADIUS_M + lat0Rad) * RAD_TO_DEG;
  const lon = (x / (EARTH_RADIUS_M * Math.cos(lat0Rad)) + lon0Rad) * RAD_TO_DEG;
  return { lat, lon };
};

export const polygonMidpoints = (points: GeoPoint[]): GeoPoint[] => {
  const normalized = normalizePolygonPoints(points);
  if (normalized.length < 2) {
    return [];
  }
  const ring = closePolygonRing(normalized);
  const midpoints: GeoPoint[] = [];
  for (let i = 0; i < ring.length - 1; i += 1) {
    const left = ring[i];
    const right = ring[i + 1];
    midpoints.push({
      lat: (left.lat + right.lat) / 2,
      lon: (left.lon + right.lon) / 2,
    });
  }
  return midpoints;
};

export const squareMetersToKm2 = (areaSquareMeters: number): number => areaSquareMeters / 1_000_000;

export const squareMetersToMi2 = (areaSquareMeters: number): number => areaSquareMeters / 2_589_988.110336;

export const formatAreaLabel = (areaSquareMeters: number): string => {
  const km2 = squareMetersToKm2(areaSquareMeters);
  const mi2 = squareMetersToMi2(areaSquareMeters);
  return `${km2.toFixed(2)} km²\n${mi2.toFixed(2)} mi²`;
};
