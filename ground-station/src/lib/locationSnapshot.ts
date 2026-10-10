import type { VehicleTelemetry } from "../types/telemetry.ts";
import type { DetectionResult, ThermalFrame } from "../types/vigil.ts";
import type { PinData } from "../types/mission.ts";
import {
  projectPerson,
  telemetryAt,
  wrap,
  type LocationConfig,
  type Terrain,
} from "./geolocation.ts";

export const LOCATION_STALE_MS = 2000;
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
}
/** Pure capture-time projection; transport and React state are kept outside it. */
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
  const capture = frame.timestamp_ms + config.frameClockOffsetMs;
  const t = telemetryAt(history, capture);
  if (
    !t ||
    Math.abs((history.at(-1)?.timestamp_ms ?? 0) - capture) > LOCATION_STALE_MS
  )
    return { ...base, message: "Waiting for synchronized GPS and attitude" };
  const heading =
    t.yaw_deg !== null && config.headingOffsetDeg !== undefined
      ? wrap(t.yaw_deg + config.headingOffsetDeg)
      : headingFor(t);
  current.detections
    .filter((d) => ["person", "human"].includes(d.class.toLowerCase()))
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
      const id = d.track_id ?? `${frame.frame_id}:${index}`;
      pins.push({
        id,
        displayLabel: String(index + 1),
        name: d.track_id ? `Person ${d.track_id}` : `Detection ${index + 1}`,
        latitude: result.latitude,
        longitude: result.longitude,
        coords: `${result.latitude.toFixed(6)}, ${result.longitude.toFixed(6)}`,
        temp:
          d.temperature_c === undefined
            ? "Unavailable"
            : `${d.temperature_c.toFixed(1)} °C`,
        status: d.temperature_status ?? "unknown",
        locationNote: `${result.method} · provisional optics / heading`,
        capturedAt: capture,
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
