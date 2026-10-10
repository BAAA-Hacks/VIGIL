import test from "node:test";
import assert from "node:assert/strict";
import {
  createPathMission,
  isPathMission,
  missionXml,
  SHAPE_POINTS,
  shapeCoordinates,
  type PathShape,
} from "../src/lib/missionPath.ts";

const shape = (kind: PathShape["kind"]): PathShape => ({
  id: kind,
  kind,
  latitude: 34.0525,
  longitude: -118.243,
  sizeM: 20,
});

test("each shape generates the requested number of distinct geographic waypoints", () => {
  for (const kind of Object.keys(SHAPE_POINTS) as PathShape["kind"][]) {
    const points = shapeCoordinates(shape(kind));
    assert.equal(points.length, SHAPE_POINTS[kind]);
    assert.equal(
      new Set(points.map((p) => `${p.latitude},${p.longitude}`)).size,
      SHAPE_POINTS[kind],
    );
    assert.ok(
      points.every(
        (p) => Number.isFinite(p.latitude) && Number.isFinite(p.longitude),
      ),
    );
  }
});

test("moving and resizing a shape changes its coordinates while preserving point count", () => {
  const original = shape("square");
  const moved = shapeCoordinates({
    ...original,
    latitude: original.latitude + 0.001,
  });
  assert.ok(
    moved.every((p) => p.latitude > shapeCoordinates(original)[0].latitude),
  );
  const large = shapeCoordinates({ ...original, sizeM: 40 });
  assert.ok(
    Math.abs(large[0].latitude - original.latitude) >
      Math.abs(shapeCoordinates(original)[0].latitude - original.latitude),
  );
  assert.equal(large.length, 4);
});

test("combined missions preserve shape order and finish with a holding WAYPOINT", () => {
  const shapes = [
    shape("circle"),
    shape("square"),
    shape("triangle"),
    shape("line"),
  ];
  const mission = createPathMission(shapes, 10, 2, "home");
  assert.equal(mission.waypoints.length, 19);
  assert.equal(mission.finish, "hold");
  const xml = missionXml(mission);
  assert.equal((xml.match(/action="WAYPOINT"/g) ?? []).length, 19);
  assert.ok(
    !xml.includes("LAND") && !xml.includes("JUMP") && !xml.includes("RTH"),
  );
  assert.match(xml, /no="19" action="WAYPOINT"/);
  assert.match(xml, /parameter1="200" parameter2="0" parameter3="0"/);
  assert.match(
    missionXml(createPathMission([shape("line")], 510, 2, "amsl")),
    /alt="510".*parameter3="1"/,
  );
});

test("malformed, oversized and invalid-altitude missions cannot be exported", () => {
  assert.equal(isPathMission(null), false);
  const mission = createPathMission([shape("line")], 10, 2, "home");
  assert.equal(isPathMission({ ...mission, finish: "land" }), false);
  assert.equal(
    isPathMission({
      ...mission,
      waypoints: Array(61).fill(mission.waypoints[0]),
    }),
    false,
  );
  for (const invalid of [0, NaN, Infinity])
    assert.throws(() => createPathMission([shape("line")], invalid, 2, "home"));
  assert.throws(() => createPathMission([shape("line")], 10, 0, "home"));
});
