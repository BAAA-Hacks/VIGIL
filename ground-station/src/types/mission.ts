import type { Detection, ThermalFrame } from "./vigil";
export interface PinData {
  review?: { frame: ThermalFrame; detection: Detection };
  manual?: boolean;
  elevationState?: "loading" | "unavailable";
  displayLabel?: string;
  locationNote?: string;
  capturedAt?: number;
  /** Detected people: false once the person has left the camera view (pin stays). */
  inView?: boolean;
  lastSeenAt?: number;
  groundElevationM?: number;
  id: string;
  name: string;
  coords: string;
  latitude: number;
  longitude: number;
  temp: string;
  status: "normal" | "elevated" | "low" | "unknown";
}
