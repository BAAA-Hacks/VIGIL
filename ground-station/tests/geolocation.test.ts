import test from "node:test";
import assert from "node:assert/strict";
import {
  CourseHeading,
  projectPerson,
  telemetryAt,
  worldRay,
  type LocationConfig,
} from "../src/lib/geolocation.ts";
import { gridTerrain } from "../src/lib/terrainGrid.ts";
import type { VehicleTelemetry } from "../src/types/telemetry.ts";
const config: LocationConfig = {
  altitudeReference: "absolute",
  takeoffElevationM: 500,
  startingCameraHeightM: 0,
  mountDownDeg: 20,
  nativeImageConfirmed: true,
  attitudeConventionConfirmed: true,
  forwardFlightConfirmed: true,
};
const packet: VehicleTelemetry = {
  timestamp_ms: 1000,
  armed: true,
  battery_v: 16,
  roll_deg: 0,
  pitch_deg: 0,
  yaw_deg: 0,
  altitude_m: 600,
  lat: 34,
  lon: -118,
  fix_valid: true,
  link_state: "connected",
  flight_mode: "OK",
  climb_ms: 0,
  satellites: 10,
  link: null,
  data_age_ms: 0,
  source: "fixture",
};
const close = (a: number, b: number, tolerance = 1e-5) =>
  assert.ok(Math.abs(a - b) < tolerance, `${a} != ${b}`);
test("center ray and absolute altitude subtract terrain, rather than adding it", () => {
  const r = projectPerson([0.4, 0.2, 0.6, 0.5], packet, 0, config);
  assert.ok(r.available);
  close(
    r.rangeM * Math.cos((20 * Math.PI) / 180),
    100 / Math.tan((20 * Math.PI) / 180),
  );
  assert.ok(r.latitude > packet.lat!);
  close(r.longitude, packet.lon!);
  const shifted = projectPerson(
    [0.4, 0.2, 0.6, 0.5],
    { ...packet, altitude_m: 1600 },
    0,
    { ...config, takeoffElevationM: 1500 },
  );
  assert.ok(shifted.available);
  close(r.rangeM, shifted.rangeM);
});
test("cardinal headings, pitch and roll follow FRD/NED convention", () => {
  for (const [heading, north, east] of [
    [0, 1, 0],
    [90, 0, 1],
    [180, -1, 0],
    [270, 0, -1],
  ]) {
    const ray = worldRay(0, 0, 20, 0, 0, heading);
    close(ray.north, north * Math.cos((20 * Math.PI) / 180));
    close(ray.east, east * Math.cos((20 * Math.PI) / 180));
  }
  close(worldRay(0, 0, 20, 10, 0, 0).down, Math.sin((10 * Math.PI) / 180));
  assert.ok(worldRay(0, 0, 20, 0, 10, 0).east < 0);
  assert.ok(worldRay(0.2, 0, 20, 0, 0, 0).east > 0);
});
test("projection withholds invalid, clipped, horizon, calibration and missing heading inputs", () => {
  for (const result of [
    projectPerson([0.4, 0.2, 0.6, 1], packet, 0, config),
    projectPerson(
      [0.4, 0.2, 0.6, 0.5],
      { ...packet, pitch_deg: 20 },
      0,
      config,
    ),
    projectPerson(
      [0.4, 0.2, 0.6, 0.5],
      { ...packet, fix_valid: false },
      0,
      config,
    ),
    projectPerson([0.4, 0.2, 0.6, 0.5], packet, null, config),
    projectPerson([0.4, 0.2, 0.6, 0.5], packet, 0, {
      ...config,
      nativeImageConfirmed: false,
    }),
    projectPerson(
      [0.4, 0.2, 0.6, 0.5],
      { ...packet, altitude_m: 400 },
      0,
      config,
    ),
  ])
    assert.equal(result.available, false);
});
test("timing brackets capture time and wraps yaw, rejects extrapolation/gaps/bad fixes", () => {
  const a = { ...packet, yaw_deg: 359 },
    b = { ...packet, timestamp_ms: 1200, yaw_deg: 1, altitude_m: 620 };
  const t = telemetryAt([a, b], 1100);
  assert.ok(t);
  close(t.yaw_deg!, 0);
  close(t.altitude_m!, 610);
  assert.equal(telemetryAt([a, b], 1300), null);
  assert.equal(telemetryAt([a, { ...b, timestamp_ms: 2000 }], 1100), null);
  assert.equal(telemetryAt([a, { ...b, fix_valid: false }], 1100), null);
});
test("course heading requires movement, three stable samples and expires", () => {
  const h = new CourseHeading();
  for (let i = 0; i < 10; i++)
    h.observe({ ...packet, timestamp_ms: i * 2000 }, true);
  assert.equal(h.heading(packet), null);
  h.reset();
  for (let i = 0; i < 4; i++)
    h.observe(
      {
        ...packet,
        timestamp_ms: 1000 + i * 2000,
        lat: 34 + i * 0.0002,
        yaw_deg: 359,
      },
      true,
    );
  const heading = h.heading({ ...packet, timestamp_ms: 7000, yaw_deg: 359 });
  assert.ok(heading !== null);
  close(heading, 0);
  assert.equal(h.heading({ ...packet, timestamp_ms: 30000 }), null);
  h.observe({ ...packet, timestamp_ms: 8000 }, false);
  assert.equal(h.heading(packet), null);
});
test("local terrain interpolation and coverage", () => {
  const terrain = gridTerrain({
    south: 33,
    west: -119,
    latitudeStep: 1,
    longitudeStep: 1,
    elevations: [
      [400, 500],
      [600, 700],
    ],
  });
  close(terrain(33.5, -118.5)!, 550);
  assert.equal(terrain(35, -118), null);
  const missing = gridTerrain({
    south: 33,
    west: -119,
    latitudeStep: 1,
    longitudeStep: 1,
    elevations: [
      [null, 500],
      [600, 700],
    ],
  });
  assert.equal(missing(33.5, -118.5), null);
});
test("terrain solver recovers flat and slope intersections, refuses uncovered terrain", () => {
  const flat = projectPerson(
    [0.4, 0.2, 0.6, 0.5],
    packet,
    0,
    config,
    () => 500,
  );
  assert.ok(flat.available);
  close(flat.rangeM, 100 / Math.sin((20 * Math.PI) / 180));
  const slope = projectPerson(
    [0.4, 0.2, 0.6, 0.5],
    packet,
    0,
    config,
    (lat) => 500 + (lat - 34) * 110922 * 0.1,
  );
  assert.ok(slope.available);
  assert.ok(slope.rangeM < flat.rangeM);
  assert.equal(
    projectPerson([0.4, 0.2, 0.6, 0.5], packet, 0, config, () => null)
      .available,
    false,
  );
});
