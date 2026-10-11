import type { VehicleTelemetry } from "../types/telemetry.ts";
import type {
  Detection,
  DetectionResult,
  ThermalFrame,
} from "../types/vigil.ts";
import type { PinData } from "../types/mission.ts";
import {
  offsetCoordinates,
  projectPerson,
  validFix,
  wrap,
  type LocationConfig,
  type Terrain,
} from "./geolocation.ts";

export const LOCATION_STALE_MS = 2000;
/** True north = magnetic + declination. Orlando, 2026: about 6.8° west. A Location settings
 * heading offset, when entered, replaces it. */
export const MAGNETIC_DECLINATION_DEG = -6.8;
/** Stand-in position for people while the drone has no GPS: every detection is pinned here. */
export interface FixedLocation {
  latitude: number;
  longitude: number;
  label: string;
}
export const UCF_BUSINESS_ADMINISTRATION: FixedLocation = {
  latitude: 28.6010014, // Business Administration I, UCF (OpenStreetMap)
  longitude: -81.1991315,
  label: "UCF Business Administration I",
};
/** Spacing between pins at the fixed location, so several people stay distinguishable. */
const FIXED_PIN_SPACING_M = 4;
export interface LocationSnapshotInput {
  active: boolean;
  frames: ThermalFrame[];
  detection: DetectionResult | null;
  config: LocationConfig | null;
  history: VehicleTelemetry[];
  now: number;
  frameReceived: number;
  telemetryReceived: number;
  terrain?: Terrain;
  testing: boolean;
  headingFor: (telemetry: VehicleTelemetry) => number | null;
  /** Used instead of projection whenever there is no fresh telemetry with a valid GPS fix. */
  fixedLocation?: FixedLocation | null;
  /** Stable spacing slot per person at the fixed location; defaults to the detection order. */
  fixedSlot?: (personId: string) => number;
}

function personPin(
  d: Detection,
  index: number,
  frame: ThermalFrame,
  latitude: number,
  longitude: number,
  locationNote: string,
): PinData {
  return {
    id: d.track_id ?? `${frame.frame_id}:${index}`,
    displayLabel: String(index + 1),
    name: d.track_id ? `Person ${d.track_id}` : `Detection ${index + 1}`,
    latitude,
    longitude,
    coords: `${latitude.toFixed(6)}, ${longitude.toFixed(6)}`,
    temp:
      d.temperature_c === undefined
        ? "Unavailable"
        : `${d.temperature_c.toFixed(1)} °C`,
    status: d.temperature_status ?? "unknown",
    locationNote,
    capturedAt: frame.timestamp_ms,
    ...(frame.payload
      ? {
          review: {
            frame: { ...frame },
            detection: { ...d, bbox_xyxy_norm: [...d.bbox_xyxy_norm] },
          },
        }
      : {}),
  };
}
/** Pure projection using the newest telemetry; transport and React state are kept outside it. */
export function locationSnapshot({
  active,
  frames,
  detection,
  config,
  history,
  now,
  frameReceived,
  telemetryReceived,
  terrain,
  testing,
  headingFor,
  fixedLocation = null,
  fixedSlot,
}: LocationSnapshotInput) {
  const frame = detection
    ? (frames.find((f) => f.frame_id === detection.frame_id) ?? null)
    : (frames.at(-1) ?? null);
  const current = frame?.frame_id === detection?.frame_id ? detection : null;
  const pins: PinData[] = [],
    reasons: string[] = [];
  const base = {
    active,
    frame,
    detection: current,
    pins,
    reasons,
    telemetry: history.at(-1) ?? null,
    drone:
      now - telemetryReceived <= LOCATION_STALE_MS
        ? (history.at(-1) ?? null)
        : null,
  };
  if (!active) return { ...base, message: "" };
  if (now - frameReceived > LOCATION_STALE_MS)
    return {
      ...base,
      detection: null,
      message: "Thermal feed stale · locations withheld",
    };
  const latest = history.at(-1);
  const liveFix =
    latest !== undefined &&
    now - telemetryReceived <= LOCATION_STALE_MS &&
    validFix(latest);
  // Fixed location until projection is possible: no GPS fix, or Location settings not applied.
  if (fixedLocation && !testing && (!liveFix || !config)) {
    if (!frame || !current)
      return { ...base, message: "Waiting for matching frame and detections" };
    current.detections
      .filter((d) => d.class === "person" || d.class === "human")
      .forEach((d, index) => {
        const slot =
          fixedSlot && d.track_id !== undefined ? fixedSlot(d.track_id) : index;
        const spot = offsetCoordinates(
          fixedLocation.latitude,
          fixedLocation.longitude,
          0,
          slot * FIXED_PIN_SPACING_M,
        );
        pins.push(
          personPin(
            d,
            index,
            frame,
            spot.latitude,
            spot.longitude,
            `Fixed location (no drone GPS) · ${fixedLocation.label}`,
          ),
        );
      });
    return {
      ...base,
      message: pins.length
        ? `Fixed location · ${fixedLocation.label}${
            liveFix
              ? " · apply Location settings to place people from the drone"
              : ""
          }`
        : "No people detected",
    };
  }
  if (!config)
    return {
      ...base,
      message:
        "Location setup required: altitude, heading and camera conventions",
    };
  if (!frame || !current)
    return { ...base, message: "Waiting for matching frame and detections" };
  if (frame.width !== 160 || frame.height !== 120)
    return {
      ...base,
      message: "Projection requires the native 160 × 120 image",
    };
  if (now - telemetryReceived > LOCATION_STALE_MS)
    return { ...base, message: "Telemetry stale · locations withheld" };
  // No camera/telemetry clock sync: pair each frame with the newest telemetry. Both feeds
  // are fresh (checked above), so the pose is at most LOCATION_STALE_MS old.
  const t = history.at(-1) ?? null;
  if (!t || !validFix(t)) return { ...base, message: "Waiting for GPS fix" };
  const heading =
    t.yaw_deg !== null && t.yaw_reference === "north"
      ? wrap(t.yaw_deg)
      : t.yaw_deg !== null && t.yaw_reference === "magnetic"
        ? wrap(
            t.yaw_deg + (config.headingOffsetDeg ?? MAGNETIC_DECLINATION_DEG),
          )
        : t.yaw_deg !== null && config.headingOffsetDeg !== undefined
          ? wrap(t.yaw_deg + config.headingOffsetDeg)
          : headingFor(t);
  current.detections
    .filter((d) => d.class === "person" || d.class === "human")
    .forEach((d, index) => {
      const result =
        d.feet_visible === false
          ? { available: false as const, reason: "Feet obscured" }
          : projectPerson(
              d.bbox_xyxy_norm,
              t,
              heading,
              config,
              testing ? undefined : terrain,
            );
      if (!result.available) {
        reasons.push(`Detection ${index + 1}: ${result.reason}`);
        return;
      }
      pins.push({
        ...personPin(
          d,
          index,
          frame,
          result.latitude,
          result.longitude,
          `${result.method} · provisional optics / heading`,
        ),
        ...(testing ? { groundElevationM: config.takeoffElevationM } : {}),
      });
    });
  return {
    ...base,
    message: pins.length
      ? terrain && !testing
        ? "Estimated coordinates · local terrain"
        : "Estimated coordinates · flat reference ground"
      : reasons.length
        ? "Locations unavailable"
        : "No people detected",
  };
}
