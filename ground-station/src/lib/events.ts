import type { VehicleTelemetry } from "../types/telemetry";
import type { DetectionResult, ThermalFrame } from "../types/vigil";
import type { LocationConfig } from "./geolocation";
import type { TerrainGrid } from "./terrainGrid";

/** Window CustomEvents forming the live adapter contract (see README). */
export const VIGIL_EVENTS = {
  telemetry: "vigil:telemetry",
  frame: "vigil:frame",
  detection: "vigil:detection",
  locationConfig: "vigil:location-config",
  terrain: "vigil:terrain",
} as const;

interface VigilEventDetail {
  telemetry: VehicleTelemetry;
  frame: ThermalFrame;
  detection: DetectionResult;
  locationConfig: LocationConfig;
  terrain: TerrainGrid | null;
}

export function dispatchVigil<K extends keyof VigilEventDetail>(
  name: K,
  detail: VigilEventDetail[K],
) {
  window.dispatchEvent(new CustomEvent(VIGIL_EVENTS[name], { detail }));
}
