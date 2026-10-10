import test from "node:test";
import assert from "node:assert/strict";
import { locationSnapshot, LOCATION_STALE_MS, type LocationSnapshotInput } from "../src/lib/locationSnapshot.ts";
import { createPinTestSample, PIN_TEST_CONFIG } from "../src/lib/pinTest.ts";
import { isLocationConfig } from "../src/lib/locationConfig.ts";

function inputs(): LocationSnapshotInput {
  const sample = createPinTestSample(10000, "data:image/png;base64,AA==");
  return { active: true, frames: [sample.frame], detection: sample.detection, config: PIN_TEST_CONFIG, history: [sample.telemetry], now: 10000, frameReceived: 10000, telemetryReceived: 10000, testing: true, headingFor: () => null };
}

test("ten person locations and the drone share synchronized test inputs", () => {
  const result = locationSnapshot(inputs());
  assert.equal(result.pins.length, 10);
  assert.ok(result.drone);
  assert.equal(new Set(result.pins.map((pin) => pin.id)).size, 10);
  for (const pin of result.pins) {
    assert.ok(Number.isFinite(pin.latitude) && Number.isFinite(pin.longitude));
    assert.equal(pin.capturedAt, 10000);
    assert.equal(pin.groundElevationM, 500);
  }
});

test("stale thermal inputs withhold pins while fresh telemetry keeps the drone", () => {
  const input = inputs();
  input.now += LOCATION_STALE_MS + 1;
  input.telemetryReceived = input.now;
  const result = locationSnapshot(input);
  assert.equal(result.pins.length, 0);
  assert.equal(result.detection, null);
  assert.ok(result.drone);
  assert.match(result.message, /Thermal feed stale/);
});

test("stale telemetry removes the drone and withholds person coordinates", () => {
  const input = inputs();
  input.now += LOCATION_STALE_MS + 1;
  input.frameReceived = input.now;
  const result = locationSnapshot(input);
  assert.equal(result.drone, null);
  assert.equal(result.pins.length, 0);
  assert.match(result.message, /Telemetry stale/);
});

test("unmatched detections and obscured feet never create speculative pins", () => {
  const input = inputs();
  input.detection = { ...input.detection!, frame_id: "unmatched" };
  assert.equal(locationSnapshot(input).pins.length, 0);
  input.detection = { ...inputs().detection!, detections: inputs().detection!.detections.map((d) => ({ ...d, feet_visible: false })) };
  const result = locationSnapshot(input);
  assert.equal(result.pins.length, 0);
  assert.equal(result.reasons.length, 10);
});

test("location conventions reject nonfinite configuration fields", () => {
  assert.ok(isLocationConfig(PIN_TEST_CONFIG));
  assert.equal(isLocationConfig({ ...PIN_TEST_CONFIG, mountDownDeg: NaN }), false);
  assert.equal(isLocationConfig({ ...PIN_TEST_CONFIG, headingOffsetDeg: Infinity }), false);
});
