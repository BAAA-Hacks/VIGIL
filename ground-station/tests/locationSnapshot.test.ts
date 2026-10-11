import test from "node:test";
import assert from "node:assert/strict";
import {
  locationSnapshot,
  LOCATION_STALE_MS,
  UCF_BUSINESS_ADMINISTRATION,
  type LocationSnapshotInput,
} from "../src/lib/locationSnapshot.ts";
import { createPinTestSample, PIN_TEST_CONFIG } from "../src/lib/pinTest.ts";
import { isLocationConfig } from "../src/lib/locationConfig.ts";

function inputs(): LocationSnapshotInput {
  const sample = createPinTestSample(10000, "data:image/png;base64,AA==");
  return {
    active: true,
    frames: [sample.frame],
    detection: sample.detection,
    config: PIN_TEST_CONFIG,
    history: [sample.telemetry],
    now: 10000,
    frameReceived: 10000,
    telemetryReceived: 10000,
    testing: true,
    headingFor: () => null,
  };
}

test("ten person locations and the drone share the test inputs", () => {
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
  input.detection = {
    ...inputs().detection!,
    detections: inputs().detection!.detections.map((d) => ({
      ...d,
      feet_visible: false,
    })),
  };
  const result = locationSnapshot(input);
  assert.equal(result.pins.length, 0);
  assert.equal(result.reasons.length, 10);
});

test("location conventions reject nonfinite configuration fields", () => {
  assert.ok(isLocationConfig(PIN_TEST_CONFIG));
  assert.equal(
    isLocationConfig({ ...PIN_TEST_CONFIG, mountDownDeg: NaN }),
    false,
  );
  assert.equal(
    isLocationConfig({ ...PIN_TEST_CONFIG, headingOffsetDeg: Infinity }),
    false,
  );
});

test("review images use the exact matched projection frame and each person's box", () => {
  const input = inputs();
  const newer = {
    ...input.frames[0],
    frame_id: "newer",
    payload: "data:image/png;base64,BB==",
  };
  input.frames.push(newer);
  const result = locationSnapshot(input);
  result.pins.forEach((pin, index) => {
    assert.equal(pin.review?.frame.frame_id, input.detection!.frame_id);
    assert.equal(pin.review?.frame.payload, input.frames[0].payload);
    assert.deepEqual(
      pin.review?.detection.bbox_xyxy_norm,
      input.detection!.detections[index].bbox_xyxy_norm,
    );
    assert.notEqual(
      pin.review?.detection.bbox_xyxy_norm,
      input.detection!.detections[index].bbox_xyxy_norm,
    );
  });
});

test("missing image payload does not substitute an unrelated capture", () => {
  const input = inputs();
  delete input.frames[0].payload;
  assert.ok(
    locationSnapshot(input).pins.every((pin) => pin.review === undefined),
  );
});

test("synthetic test pins and drone stay near UCF", () => {
  const input = inputs();
  const result = locationSnapshot(input);
  assert.equal(input.history[0].lat, 28.601667);
  assert.equal(input.history[0].lon, -81.200556);
  for (const pin of result.pins) {
    assert.ok(Math.abs(pin.latitude - 28.601667) < 0.03);
    assert.ok(Math.abs(pin.longitude + 81.200556) < 0.035);
  }
});

test("frames pair with the newest telemetry without a shared clock", () => {
  const input = inputs();
  input.frames = [{ ...input.frames[0], timestamp_ms: 987654321 }];
  const result = locationSnapshot(input);
  assert.equal(result.pins.length, 10);
});

test("an invalid GPS fix withholds pins", () => {
  const input = inputs();
  input.history = [{ ...input.history[0], fix_valid: false }];
  const result = locationSnapshot(input);
  assert.equal(result.pins.length, 0);
  assert.match(result.message, /GPS fix/);
});

test("without a GPS fix, people are pinned at the fixed location", () => {
  const input = inputs();
  input.testing = false;
  input.config = null;
  input.history = [];
  input.telemetryReceived = 0;
  input.fixedLocation = UCF_BUSINESS_ADMINISTRATION;
  const result = locationSnapshot(input);
  assert.equal(result.pins.length, 10);
  assert.ok(
    Math.abs(result.pins[0].latitude - UCF_BUSINESS_ADMINISTRATION.latitude) <
      1e-9,
  );
  assert.ok(
    Math.abs(result.pins[0].longitude - UCF_BUSINESS_ADMINISTRATION.longitude) <
      1e-9,
  );
  assert.equal(new Set(result.pins.map((pin) => pin.longitude)).size, 10);
  assert.match(result.pins[0].locationNote ?? "", /Fixed location/);
  assert.match(result.message, /Fixed location/);
});

test("a live GPS fix overrides the fixed location", () => {
  const input = inputs();
  input.testing = false;
  input.fixedLocation = UCF_BUSINESS_ADMINISTRATION;
  const result = locationSnapshot(input);
  assert.ok(
    result.pins.every((pin) => !/Fixed location/.test(pin.locationNote ?? "")),
  );
});
