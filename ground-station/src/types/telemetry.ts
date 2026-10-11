export interface VehicleTelemetry {
  timestamp_ms: number;
  armed: boolean | null;
  battery_v: number | null;
  roll_deg: number | null;
  pitch_deg: number | null;
  yaw_deg: number | null;
  altitude_m: number | null;
  lat: number | null;
  lon: number | null;
  fix_valid: boolean | null;
  link_state: string;
  flight_mode: string | null;
  climb_ms: number | null;
  satellites: number | null;
  link: {
    uplink_lq: number;
    uplink_rssi_dbm: number;
    downlink_lq: number;
    downlink_rssi_dbm: number;
  } | null;
  data_age_ms: number | null;
  source: string;
  yaw_reference?: string;
  speed_ms?: number | null;
  course_deg?: number | null;
  distance_home_m?: number | null;
  pcb_temp_c?: number | null;
  /** Above mean sea level, m: barometric height plus a GPS-learned offset (altitude_m is above home). */
  altitude_msl_m?: number | null;
  battery_pct?: number | null;
  home?: { lat: number; lon: number } | null;
  /** Raw IMU from the ground-telemetry firmware: accelerometer in g, gyro in °/s (board axes). */
  imu?: {
    accel_g: [number, number, number];
    gyro_dps: [number, number, number];
  } | null;
  /** Magnetometer: INAV counts (not a physical unit); heading is magnetic only when calibrated. */
  mag?: {
    field_counts: [number, number, number];
    heading_deg: number;
    healthy: boolean;
    calibrated: boolean;
  } | null;
}
