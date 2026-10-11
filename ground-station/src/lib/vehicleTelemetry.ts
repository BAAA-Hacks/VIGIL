import type { VehicleTelemetry } from "../types/telemetry";
export function isVehicleTelemetry(value: unknown): value is VehicleTelemetry {
  if (typeof value !== "object" || value === null) return false;
  const record = value as Record<string, unknown>;
  const finite = (item: unknown) =>
    typeof item === "number" && Number.isFinite(item);
  const numericFields = [
    "battery_v",
    "roll_deg",
    "pitch_deg",
    "yaw_deg",
    "altitude_m",
    "lat",
    "lon",
    "climb_ms",
    "satellites",
    "data_age_ms",
  ];
  if (
    !finite(record.timestamp_ms) ||
    !numericFields.every((key) => record[key] === null || finite(record[key]))
  )
    return false;
  if (
    ![record.armed, record.fix_valid].every(
      (item) => item === null || typeof item === "boolean",
    )
  )
    return false;
  if (
    typeof record.link_state !== "string" ||
    typeof record.source !== "string" ||
    !(record.flight_mode === null || typeof record.flight_mode === "string")
  )
    return false;
  const optionalNumbers = [
    "speed_ms",
    "course_deg",
    "distance_home_m",
    "pcb_temp_c",
    "battery_pct",
    "altitude_msl_m",
  ];
  if (
    !optionalNumbers.every(
      (key) =>
        record[key] === undefined ||
        record[key] === null ||
        finite(record[key]),
    )
  )
    return false;
  if (
    ["speed_ms", "distance_home_m"].some(
      (key) => typeof record[key] === "number" && record[key] < 0,
    )
  )
    return false;
  if (
    typeof record.battery_pct === "number" &&
    (record.battery_pct < 0 || record.battery_pct > 100)
  )
    return false;
  if (record.home !== undefined && record.home !== null) {
    if (typeof record.home !== "object") return false;
    const home = record.home as Record<string, unknown>;
    if (
      !finite(home.lat) ||
      !finite(home.lon) ||
      Math.abs(home.lat as number) > 90 ||
      Math.abs(home.lon as number) > 180
    )
      return false;
  }
  const vector = (item: unknown) =>
    Array.isArray(item) && item.length === 3 && item.every(finite);
  if (record.imu !== undefined && record.imu !== null) {
    if (typeof record.imu !== "object") return false;
    const imu = record.imu as Record<string, unknown>;
    if (!vector(imu.accel_g) || !vector(imu.gyro_dps)) return false;
  }
  if (record.mag !== undefined && record.mag !== null) {
    if (typeof record.mag !== "object") return false;
    const mag = record.mag as Record<string, unknown>;
    if (
      !vector(mag.field_counts) ||
      !finite(mag.heading_deg) ||
      (mag.heading_deg as number) < 0 ||
      (mag.heading_deg as number) >= 360 ||
      typeof mag.healthy !== "boolean" ||
      typeof mag.calibrated !== "boolean"
    )
      return false;
  }
  if (record.link !== null) {
    if (typeof record.link !== "object" || !record.link) return false;
    const link = record.link as Record<string, unknown>;
    if (
      ![
        "uplink_lq",
        "uplink_rssi_dbm",
        "downlink_lq",
        "downlink_rssi_dbm",
      ].every((key) => finite(link[key]))
    )
      return false;
  }
  return (
    (record.lat === null || Math.abs(record.lat as number) <= 90) &&
    (record.lon === null || Math.abs(record.lon as number) <= 180)
  );
}
