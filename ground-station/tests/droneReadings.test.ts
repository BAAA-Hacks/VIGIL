import test from "node:test";
import assert from "node:assert/strict";
import { createPinTestSample, PIN_TEST_CONFIG } from "../src/lib/pinTest.ts";
import { getDroneReadings } from "../src/lib/droneReadings.ts";
import { isVehicleTelemetry } from "../src/lib/vehicleTelemetry.ts";

test("pin hover fills drone info and retains the 10 m ground clearance", () => {
  const { telemetry } = createPinTestSample(
    100000,
    "data:image/png;base64,test",
  );
  const readings = new Map(
    getDroneReadings(telemetry, "00:12").map((r) => [r.label, r.value]),
  );
  assert.equal(readings.get("Ground speed"), "0.0 m/s");
  assert.equal(readings.get("Distance from home"), "0.0 m");
  assert.equal(readings.get("PCB temperature"), "38.5 °C");
  assert.equal(readings.get("Altitude (sea level)"), "510.0 m");
  assert.equal(readings.get("Roll / pitch"), "0.4 ° / -0.6 °");
  assert.equal(readings.get("Flight time"), "00:12");
  assert.equal(readings.get("Course"), "0.0 °");
  assert.equal(
    readings.get("Accelerometer (x / y / z)"),
    "0.01 / -0.01 / 1.00 g",
  );
  assert.equal(readings.get("Gyro (x / y / z)"), "0.2 / -0.1 / 0.0 °/s");
  assert.equal(readings.get("Compass"), "0.0 ° · Calibrated");
  assert.equal(telemetry.altitude_m! - PIN_TEST_CONFIG.takeoffElevationM!, 10);
  assert.ok(
    [...readings.values()].every((value) => !value.includes("Unavailable")),
  );
});

test("roll/pitch display signed degrees; optional fields preserve old packet compatibility", () => {
  const { telemetry } = createPinTestSample(
    100000,
    "data:image/png;base64,test",
  );
  const readings = getDroneReadings(
    { ...telemetry, pitch_deg: 359.4 },
    "00:00",
  );
  assert.equal(
    readings.find((r) => r.label === "Roll / pitch")?.value,
    "0.4 ° / -0.6 °",
  );
  assert.equal(isVehicleTelemetry({ ...telemetry, speed_ms: "fast" }), false);
  assert.equal(
    isVehicleTelemetry({ ...telemetry, distance_home_m: -2 }),
    false,
  );
  assert.equal(isVehicleTelemetry({ ...telemetry, pcb_temp_c: NaN }), false);
  const old: Record<string, unknown> = { ...telemetry };
  for (const field of [
    "speed_ms",
    "course_deg",
    "distance_home_m",
    "pcb_temp_c",
    "battery_pct",
    "home",
    "imu",
    "mag",
    "altitude_msl_m",
  ])
    delete old[field];
  assert.equal(isVehicleTelemetry(old), true);
});

test("IMU and compass extras are validated and shown honestly", () => {
  const { telemetry } = createPinTestSample(
    100000,
    "data:image/png;base64,test",
  );
  const mag = {
    field_counts: [-28, 344, 905],
    heading_deg: 95.9,
    healthy: true,
    calibrated: false,
  };
  assert.equal(
    isVehicleTelemetry({ ...telemetry, imu: null, mag: null }),
    true,
  );
  assert.equal(
    isVehicleTelemetry({
      ...telemetry,
      imu: { accel_g: [0, 0], gyro_dps: [0, 0, 0] },
    }),
    false,
  );
  assert.equal(
    isVehicleTelemetry({ ...telemetry, mag: { ...mag, heading_deg: 360 } }),
    false,
  );
  assert.equal(
    isVehicleTelemetry({ ...telemetry, mag: { ...mag, calibrated: "no" } }),
    false,
  );
  const compass = (value: unknown) =>
    getDroneReadings(
      { ...telemetry, mag: value as typeof telemetry.mag },
      "00:00",
    ).find((r) => r.label === "Compass")?.value;
  assert.equal(compass(mag), "95.9 ° · Not calibrated");
  assert.equal(compass({ ...mag, healthy: false }), "Not responding");
  assert.equal(compass(null), "Unavailable");
});
