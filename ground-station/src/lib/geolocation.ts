import type { VehicleTelemetry } from "../types/telemetry.ts";
import type { BoundingBox } from "../types/vigil.ts";

const rad = Math.PI / 180;
export const wrap = (angle: number) => ((angle % 360) + 360) % 360;
const delta = (a: number, b: number) => ((b - a + 540) % 360) - 180;
export interface LocationConfig {
  altitudeReference: "takeoff" | "absolute";
  /** Absolute mode requires a locally supplied takeoff terrain elevation in the same datum. */
  takeoffElevationM?: number;
  startingCameraHeightM: number;
  mountDownDeg: number;
  /** Confirmed raw sensor image: no crop, mirror, rotation or letterboxing. */
  nativeImageConfirmed: boolean;
  /** FRD/NED, pitch nose-up, roll right-wing-down, yaw clockwise. */
  attitudeConventionConfirmed: boolean;
  /** Allows GPS course calibration only during known forward flight. */
  forwardFlightConfirmed: boolean;
  headingOffsetDeg?: number;
  fx?: number;
  fy?: number;
  cx?: number;
  cy?: number;
}
export type LocationResult =
  | { available: false; reason: string }
  | {
      available: true;
      latitude: number;
      longitude: number;
      rangeM: number;
      method: string;
    };
export type Terrain = (latitude: number, longitude: number) => number | null;
const unavailable = (reason: string): LocationResult => ({
  available: false,
  reason,
});

export function validFix(t: VehicleTelemetry): boolean {
  return (
    t.fix_valid === true &&
    t.lat !== null &&
    t.lon !== null &&
    Number.isFinite(t.lat) &&
    Number.isFinite(t.lon) &&
    Math.abs(t.lat) < 85 &&
    Math.abs(t.lon) <= 180 &&
    t.link_state === "connected" &&
    t.data_age_ms !== null &&
    t.data_age_ms <= 1000 &&
    t.data_age_ms >= 0
  );
}
/** WGS84 local tangent approximation, limited by projection to 2 km and |latitude| <85. */
export function offsetCoordinates(
  lat: number,
  lon: number,
  north: number,
  east: number,
) {
  const a = 6378137,
    e2 = 0.00669437999014;
  const q = 1 - e2 * Math.sin(lat * rad) ** 2;
  const meridian = (a * (1 - e2)) / q ** 1.5;
  const prime = a / Math.sqrt(q);
  return {
    latitude: lat + north / meridian / rad,
    longitude:
      ((lon + east / (prime * Math.cos(lat * rad)) / rad + 540) % 360) - 180,
  };
}
export function worldRay(
  x: number,
  y: number,
  mount: number,
  pitch: number,
  roll: number,
  heading: number,
) {
  const s = (v: number) => Math.sin(v * rad),
    c = (v: number) => Math.cos(v * rad);
  const f = c(mount) - y * s(mount),
    r = x,
    d = s(mount) + y * c(mount);
  const rr = c(roll) * r - s(roll) * d,
    dd = s(roll) * r + c(roll) * d;
  const ff = c(pitch) * f + s(pitch) * dd,
    down = -s(pitch) * f + c(pitch) * dd;
  const north = c(heading) * ff - s(heading) * rr,
    east = s(heading) * ff + c(heading) * rr;
  const length = Math.hypot(north, east, down);
  return { north: north / length, east: east / length, down: down / length };
}
export function projectPerson(
  box: BoundingBox,
  t: VehicleTelemetry,
  heading: number | null,
  config: LocationConfig,
  terrain?: Terrain,
): LocationResult {
  if (!config.nativeImageConfirmed)
    return unavailable("Confirm native image orientation");
  if (!config.attitudeConventionConfirmed)
    return unavailable("Confirm attitude conventions");
  if (!validFix(t)) return unavailable("Valid fresh GPS fix required");
  if (heading === null || !Number.isFinite(heading))
    return unavailable("North heading unavailable");
  if (
    t.altitude_m === null ||
    t.roll_deg === null ||
    t.pitch_deg === null ||
    ![t.altitude_m, t.roll_deg, t.pitch_deg].every(Number.isFinite)
  )
    return unavailable("Altitude or attitude missing");
  if (
    !box.every(Number.isFinite) ||
    box.some((v) => v < 0 || v > 1) ||
    box[2] <= box[0] ||
    box[3] <= box[1]
  )
    return unavailable("Invalid detection box");
  if (box[0] <= 0 || box[1] <= 0 || box[2] >= 1 || box[3] >= 0.99)
    return unavailable("Ground contact clipped");
  if (
    ![config.startingCameraHeightM, config.mountDownDeg].every(
      Number.isFinite,
    ) ||
    config.startingCameraHeightM < 0 ||
    config.mountDownDeg < 0 ||
    config.mountDownDeg > 90
  )
    return unavailable("Invalid camera configuration");
  const fx = config.fx ?? 80 / Math.tan(28.5 * rad),
    fy = config.fy ?? fx;
  const cx = config.cx ?? 79.5,
    cy = config.cy ?? 59.5;
  if (![fx, fy, cx, cy].every(Number.isFinite) || fx <= 0 || fy <= 0)
    return unavailable("Invalid camera intrinsics");
  // Normalized image edge coordinates -> sensor pixel-center coordinates.
  const u = ((box[0] + box[2]) / 2) * 160 - 0.5,
    v = box[3] * 120 - 0.5;
  const ray = worldRay(
    (u - cx) / fx,
    (v - cy) / fy,
    config.mountDownDeg,
    t.pitch_deg,
    t.roll_deg,
    heading,
  );
  if (ray.down < Math.sin(3 * rad))
    return unavailable("Ray above or near horizon");
  const base = config.takeoffElevationM;
  if (
    config.altitudeReference === "absolute" &&
    (base === undefined || !Number.isFinite(base))
  )
    return unavailable("Takeoff terrain elevation required");
  const cameraElevation =
    (config.altitudeReference === "takeoff" ? (base ?? 0) : 0) +
    t.altitude_m +
    config.startingCameraHeightM;
  const point = (distance: number) =>
    offsetCoordinates(
      t.lat!,
      t.lon!,
      ray.north * distance,
      ray.east * distance,
    );
  const ground = terrain ?? (() => base ?? 0);
  const clearance = (distance: number) => {
    const p = point(distance),
      elevation = ground(p.latitude, p.longitude);
    return elevation === null || !Number.isFinite(elevation)
      ? null
      : cameraElevation - distance * ray.down - elevation;
  };
  const start = clearance(0);
  if (start === null || start <= 0)
    return unavailable("Ground coverage or positive camera height required");
  let lo = 0,
    hi = 0;
  // Find first sampled crossing, then bisect. Terrain resolution must support 5 m steps.
  for (let distance = 5; distance <= 2000; distance += 5) {
    const value = clearance(distance);
    if (value === null)
      return unavailable("Terrain coverage missing along ray");
    if (value <= 0) {
      hi = distance;
      break;
    }
    lo = distance;
  }
  if (!hi) return unavailable("Intersection exceeds 2 km range");
  for (let i = 0; i < 24; i++) {
    const mid = (lo + hi) / 2,
      value = clearance(mid);
    if (value === null) return unavailable("Terrain coverage missing");
    if (value > 0) lo = mid;
    else hi = mid;
  }
  return {
    available: true,
    ...point(hi),
    rangeM: hi,
    method: terrain
      ? "Estimated · local terrain"
      : "Estimated · flat reference ground",
  };
}

/** Bracket only; no arrival-time substitution or unbounded extrapolation. */
export function telemetryAt(
  history: VehicleTelemetry[],
  time: number,
): VehicleTelemetry | null {
  const exact = history.find((t) => t.timestamp_ms === time);
  if (exact) return validFix(exact) ? exact : null;
  const i = history.findIndex((t) => t.timestamp_ms > time);
  if (i <= 0) return null;
  const a = history[i - 1],
    b = history[i];
  if (!validFix(a) || !validFix(b) || b.timestamp_ms - a.timestamp_ms > 500)
    return null;
  const f = (time - a.timestamp_ms) / (b.timestamp_ms - a.timestamp_ms);
  const linear = (x: number | null, y: number | null) =>
    x === null || y === null ? null : x + f * (y - x);
  const angle = (x: number | null, y: number | null) =>
    x === null || y === null ? null : wrap(x + f * delta(x, y));
  if (
    a.yaw_deg === null ||
    b.yaw_deg === null ||
    Math.abs(delta(a.yaw_deg, b.yaw_deg)) > 30
  )
    return null;
  return {
    ...a,
    timestamp_ms: time,
    lat: linear(a.lat, b.lat),
    lon: a.lon! + f * delta(a.lon!, b.lon!),
    altitude_m: linear(a.altitude_m, b.altitude_m),
    roll_deg: linear(a.roll_deg, b.roll_deg),
    pitch_deg: linear(a.pitch_deg, b.pitch_deg),
    yaw_deg: angle(a.yaw_deg, b.yaw_deg),
  };
}

export class CourseHeading {
  private anchor: VehicleTelemetry | null = null;
  private offsets: { value: number; time: number }[] = [];
  reset() {
    this.anchor = null;
    this.offsets = [];
  }
  observe(t: VehicleTelemetry, forward: boolean) {
    if (
      !validFix(t) ||
      t.yaw_deg === null ||
      !forward ||
      t.roll_deg === null ||
      t.pitch_deg === null ||
      Math.abs(t.roll_deg) > 10 ||
      Math.abs(t.pitch_deg) > 15
    ) {
      this.reset();
      return;
    }
    const a = this.anchor;
    if (!a) {
      this.anchor = t;
      return;
    }
    const elapsed = t.timestamp_ms - a.timestamp_ms;
    if (
      elapsed <= 0 ||
      elapsed > 5000 ||
      a.source !== t.source ||
      a.yaw_reference !== t.yaw_reference ||
      Math.abs(delta(a.yaw_deg!, t.yaw_deg)) > 5
    ) {
      this.reset();
      this.anchor = t;
      return;
    }
    if (elapsed < 2000) return;
    const north = (t.lat! - a.lat!) * rad * 6371000;
    const east = delta(a.lon!, t.lon!) * rad * 6371000 * Math.cos(t.lat! * rad);
    const distance = Math.hypot(north, east),
      speed = distance / (elapsed / 1000);
    if (distance >= 10 && speed >= 2 && speed <= 60) {
      this.offsets.push({
        value: wrap(Math.atan2(east, north) / rad - t.yaw_deg),
        time: t.timestamp_ms,
      });
      this.offsets = this.offsets.slice(-8);
    }
    this.anchor = t;
  }
  heading(t: VehicleTelemetry): number | null {
    if (t.yaw_deg === null) return null;
    const samples = this.offsets.filter(
      (s) => Math.abs(t.timestamp_ms - s.time) <= 15000,
    );
    if (samples.length < 3) return null;
    const x = samples.reduce((sum, s) => sum + Math.cos(s.value * rad), 0);
    const y = samples.reduce((sum, s) => sum + Math.sin(s.value * rad), 0);
    if (Math.hypot(x, y) / samples.length < 0.98) return null;
    return wrap(t.yaw_deg + Math.atan2(y, x) / rad);
  }
}
