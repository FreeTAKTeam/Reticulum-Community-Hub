import type { FeatureCollection } from "geojson";
import { get } from "./client";
import type { ApiError } from "./client";
export interface SensorProjection {
  state: {sensorId: string; sampleAtMs: number; azimuthDeg: number | null; elevationDeg: number | null;
    horizontalFovDeg: number | null; verticalFovDeg: number | null; rollDeg: number | null;
    imageNorthDeg: number | null; slantRangeM: number | null; rangeKind: string};
  manifest: {label?: string; video?: {protocol: string; endpointRef: string}} | null;
  display: {stale: boolean; positionStale: boolean; unsynchronized: boolean; geojson: FeatureCollection};
}
export interface SensorOrigin {
  originId: string; writerId: string; originKind: string; label: string;
  position: {lat: number; lon: number; altM: number | null} | null; sensors: SensorProjection[];
}
export async function sensorOrigins(): Promise<{items: SensorOrigin[]; observedAtMs: number}> {
  try {
    const response = await get<{items: SensorOrigin[]; observedAtMs: number}>("/Sensors", {retries: 0});
    if (!Array.isArray(response.items) || !Number.isFinite(response.observedAtMs)) throw new Error("Invalid sensor snapshot");
    return response;
  } catch (error) {
    // The shared UI also serves Python 2.9, which has no sensor-extension endpoint.
    if ((error as ApiError).status === 404) return {items: [], observedAtMs: Date.now()};
    throw error;
  }
}
