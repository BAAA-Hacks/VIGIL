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
