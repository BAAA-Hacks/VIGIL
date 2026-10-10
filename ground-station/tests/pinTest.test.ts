import test from "node:test";
import assert from "node:assert/strict";
import {
  createPinTestSample,
  PIN_TEST_CONFIG,
  pinTestPixels,
} from "../src/lib/pinTest.ts";
import {
  projectPerson,
  telemetryAt,
  validFix,
} from "../src/lib/geolocation.ts";

test("complete drone and thermal input packets create ten unique person locations", () => {
  const sample = createPinTestSample(
    100000,
    "data:image/png;base64,test-fixture",
  );
  assert.equal(sample.telemetry.source, "synthetic-pin-test");
  assert.equal(validFix(sample.telemetry), true);
  assert.equal(sample.frame.width, 160);
  assert.equal(sample.frame.height, 120);
  assert.equal(sample.frame.frame_id, sample.detection.frame_id);
  assert.equal(sample.frame.timestamp_ms, sample.telemetry.timestamp_ms);
  const captured = telemetryAt([sample.telemetry], sample.frame.timestamp_ms);
  assert.ok(captured);
  assert.equal(sample.detection.detections.length, 10);
  const coordinates = new Set<string>();
  for (const detection of sample.detection.detections) {
    assert.equal("latitude" in detection, false);
    const projected = projectPerson(
      detection.bbox_xyxy_norm,
      captured,
      captured.yaw_deg! + PIN_TEST_CONFIG.headingOffsetDeg!,
      PIN_TEST_CONFIG,
    );
    assert.ok(projected.available, projected.available ? "" : projected.reason);
    assert.ok(projected.latitude > captured.lat!);
    coordinates.add(`${projected.latitude},${projected.longitude}`);
  }
  assert.equal(coordinates.size, 10);
  const next = createPinTestSample(100200, sample.frame.payload!);
  assert.notEqual(sample.frame.frame_id, next.frame.frame_id);
  assert.deepEqual(
    sample.detection.detections.map((d) => d.track_id),
    next.detection.detections.map((d) => d.track_id),
  );
});
test("thermal silhouettes occupy the same supplied detection boxes", () => {
  const sample = createPinTestSample(
    100000,
    "data:image/png;base64,test-fixture",
  );
  const pixels = pinTestPixels();
  assert.equal(pixels.length, 160 * 120 * 4);
  for (const d of sample.detection.detections) {
    const [left, top, right, bottom] = d.bbox_xyxy_norm;
    const x = Math.round(((left + right) / 2) * 160),
      y = Math.round((top + (bottom - top) * 0.5) * 120);
    assert.ok(pixels[(y * 160 + x) * 4] > 170);
  }
  assert.ok(pixels[0] < 60);
});
