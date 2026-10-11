import test from "node:test";
import assert from "node:assert/strict";
import { createPinTestSample } from "../src/lib/pinTest.ts";
import { markerHeading } from "../src/lib/droneHeading.ts";

const { telemetry } = createPinTestSample(100000, "data:image/png;base64,test");

test("arrow follows the magnetometer heading, even while hovering", () => {
  const h = markerHeading(
    {
      ...telemetry,
      yaw_deg: 270,
      yaw_reference: "magnetic",
      course_deg: 90,
      speed_ms: 0,
    },
    45,
  );
  assert.deepEqual(h, {
    deg: 270,
    source: "nose",
    current: true,
    lastCourse: 45,
  });
});

test("without a magnetometer the arrow uses GPS course, dimmed while hovering", () => {
  const relative = { ...telemetry, yaw_deg: 270, yaw_reference: "relative" };
  const moving = markerHeading(
    { ...relative, course_deg: 90, speed_ms: 3 },
    null,
  );
  assert.deepEqual(moving, {
    deg: 90,
    source: "course",
    current: true,
    lastCourse: 90,
  });
  const hovering = markerHeading(
    { ...relative, course_deg: 10, speed_ms: 0.1 },
    moving.lastCourse,
  );
  assert.deepEqual(hovering, {
    deg: 90,
    source: "course",
    current: false,
    lastCourse: 90,
  });
  assert.equal(
    markerHeading({ ...relative, course_deg: null }, null).deg,
    null,
  );
});

test("the replay track's north-referenced yaw also points the arrow", () => {
  const h = markerHeading(
    { ...telemetry, yaw_deg: 135, yaw_reference: "north", speed_ms: 0 },
    null,
  );
  assert.equal(h.deg, 135);
  assert.equal(h.source, "nose");
});
