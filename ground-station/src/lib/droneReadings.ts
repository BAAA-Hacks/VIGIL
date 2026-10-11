import type { VehicleTelemetry } from "../types/telemetry";

const unavailable = "Unavailable";

/** Whole seconds as mm:ss. */
export function formatClock(seconds: number) {
  const minutes = Math.floor(seconds / 60).toString();
  return `${minutes.padStart(2, "0")}:${(seconds % 60).toString().padStart(2, "0")}`;
}

function formatNumber(value: number | null | undefined, unit: string) {
  return value == null ? unavailable : value.toFixed(1) + " " + unit;
}

function formatSignedAngle(value: number | null | undefined) {
  if (value == null) return unavailable;
  return formatNumber(((((value + 180) % 360) + 360) % 360) - 180, "°");
}

function formatVector(
  value: readonly number[] | undefined,
  digits: number,
  unit: string,
) {
  return value
    ? value.map((v) => v.toFixed(digits)).join(" / ") + " " + unit
    : unavailable;
}

function formatCompass(mag: VehicleTelemetry["mag"]) {
  if (!mag) return unavailable;
  if (!mag.healthy) return "Not responding";
  return (
    mag.heading_deg.toFixed(1) +
    " ° · " +
    (mag.calibrated ? "Calibrated" : "Not calibrated")
  );
}

function formatFix(value: boolean | null) {
  return value === null ? "Unknown" : value ? "Valid" : "No fix";
}

function formatLink(
  link: VehicleTelemetry["link"],
  direction: "uplink" | "downlink",
) {
  if (!link) return unavailable;
  return direction === "uplink"
    ? link.uplink_lq + "% / " + link.uplink_rssi_dbm + " dBm"
    : link.downlink_lq + "% / " + link.downlink_rssi_dbm + " dBm";
}

export function getDroneReadings(
  data: VehicleTelemetry | null,
  flightTime: string,
) {
  const coordinates =
    data?.fix_valid && data.lat !== null && data.lon !== null
      ? data.lat.toFixed(5) + ", " + data.lon.toFixed(5)
      : unavailable;
  const armed =
    data?.armed == null ? "Unknown" : data.armed ? "Armed" : "Disarmed";

  return [
    {
      label: "Altitude (above home)",
      value: formatNumber(data?.altitude_m, "m"),
    },
    {
      label: data?.yaw_reference === "relative" ? "Relative yaw" : "Yaw",
      value: formatNumber(data?.yaw_deg, "°"),
    },
    {
      label: "Roll / pitch",
      value: data
        ? formatSignedAngle(data.roll_deg) +
          " / " +
          formatSignedAngle(data.pitch_deg)
        : unavailable,
    },
    { label: "Course", value: formatNumber(data?.course_deg, "°") },
    { label: "Climb rate", value: formatNumber(data?.climb_ms, "m/s") },
    { label: "Coordinates", value: coordinates },
    {
      label: "Arming / mode",
      value: data
        ? armed + " · " + (data.flight_mode ?? "Unknown")
        : unavailable,
    },
    { label: "Ground speed", value: formatNumber(data?.speed_ms, "m/s") },
    {
      label: "Distance from home",
      value: formatNumber(data?.distance_home_m, "m"),
    },
    { label: "Flight time", value: flightTime },
    {
      label: "Altitude (sea level)",
      value: formatNumber(data?.altitude_msl_m, "m"),
    },
    {
      label: "Satellites / GPS fix",
      value: data
        ? (data.satellites ?? "—") + " / " + formatFix(data.fix_valid)
        : unavailable,
    },
    {
      label: "Accelerometer (x / y / z)",
      value: formatVector(data?.imu?.accel_g, 2, "g"),
    },
    {
      label: "Gyro (x / y / z)",
      value: formatVector(data?.imu?.gyro_dps, 1, "°/s"),
    },
    { label: "Compass", value: formatCompass(data?.mag) },
    {
      label: "Uplink quality / RSSI",
      value: formatLink(data?.link ?? null, "uplink"),
    },
    {
      label: "Downlink quality / RSSI",
      value: formatLink(data?.link ?? null, "downlink"),
    },
  ];
}
