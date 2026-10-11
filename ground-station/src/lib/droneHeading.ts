import type { VehicleTelemetry } from "../types/telemetry";

/** Below this ground speed GPS course is noise, so the last good course is kept. */
export const MIN_COURSE_SPEED_MS = 0.5;

export interface MarkerHeading {
  /** Degrees clockwise from north, or null when no direction is known yet. */
  deg: number | null;
  /** "nose" = north-referenced yaw (magnetometer or replay track); "course" = GPS direction of travel. */
  source: "nose" | "course" | null;
  /** Full strength for a live heading; dimmed for a remembered course while hovering. */
  current: boolean;
  /** Course to remember for the next packet. */
  lastCourse: number | null;
}

/**
 * Direction for the drone marker's arrow. A north-referenced yaw (yaw_reference "magnetic" from a
 * calibrated magnetometer, or "north" from the replay track) gives the nose direction even while hovering; otherwise fall back to GPS course over ground,
 * which is only meaningful while moving, so a hovering drone keeps its last good course, dimmed.
 */
export function markerHeading(
  drone: VehicleTelemetry,
  lastCourse: number | null,
): MarkerHeading {
  const moving =
    drone.course_deg !== undefined &&
    drone.course_deg !== null &&
    Number.isFinite(drone.course_deg) &&
    (drone.speed_ms ?? 0) >= MIN_COURSE_SPEED_MS;
  const course = moving ? drone.course_deg! : lastCourse;
  if (
    (drone.yaw_reference === "magnetic" || drone.yaw_reference === "north") &&
    drone.yaw_deg !== null &&
    Number.isFinite(drone.yaw_deg)
  )
    return {
      deg: drone.yaw_deg,
      source: "nose",
      current: true,
      lastCourse: course,
    };
  return {
    deg: course,
    source: course === null ? null : "course",
    current: moving,
    lastCourse: course,
  };
}
