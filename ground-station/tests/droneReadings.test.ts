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
  assert.equal(readings.get("Roll / pitch"), "0.4 ° / -0.6 °");
  assert.equal(readings.get("Flight time"), "00:12");
  assert.equal(readings.get("Course"), "0.0 °");
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
  ])
    delete old[field];
  assert.equal(isVehicleTelemetry(old), true);
});
