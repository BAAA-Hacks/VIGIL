import test from "node:test";
import assert from "node:assert/strict";
import {
  moveShapePoint,
  shapeCoordinates,
  createPathMission,
  missionXml,
  SHAPE_POINTS,
  type PathShape,
} from "../src/lib/missionPath.ts";
import { offsetCoordinates } from "../src/lib/geolocation.ts";

const base = (kind: PathShape["kind"]): PathShape => ({
  id: kind,
  kind,
  latitude: 34.0525,
  longitude: -118.243,
  sizeM: 20,
});
test("every shape's waypoint can move independently and its real coordinates reach mission export", () => {
  for (const kind of Object.keys(SHAPE_POINTS) as PathShape["kind"][]) {
    const original = base(kind),
      before = shapeCoordinates(original);
    const target = offsetCoordinates(
      original.latitude,
      original.longitude,
      35,
      13,
    );
    const edited = moveShapePoint(
      original,
      1,
      target.latitude,
      target.longitude,
    );
    const after = shapeCoordinates(edited);
    assert.equal(after.length, SHAPE_POINTS[kind]);
    assert.ok(Math.abs(after[1].latitude - target.latitude) < 1e-9);
    assert.ok(Math.abs(after[1].longitude - target.longitude) < 1e-9);
    after.forEach((point, index) => {
      if (index !== 1) assert.deepEqual(point, before[index]);
    });
    assert.equal(original.vertexOffsets, undefined);
    const mission = createPathMission([edited], 10, 2, "home");
    assert.deepEqual(mission.waypoints[1], {
      ...after[1],
      altitudeM: 10,
      speedMs: 2,
    });
    assert.ok(
      missionXml(mission).includes(
        `lat="${target.latitude.toFixed(7)}" lon="${target.longitude.toFixed(7)}"`,
      ),
    );
    assert.equal(mission.finish, "hold");
  }
});

test("custom corners retain their geometry through whole-shape moves and resizing", () => {
  const original = base("square");
  const target = offsetCoordinates(
    original.latitude,
    original.longitude,
    35,
    13,
  );
  const edited = moveShapePoint(original, 1, target.latitude, target.longitude);
  const resized = shapeCoordinates({ ...edited, sizeM: 40 });
  const expected = offsetCoordinates(
    original.latitude,
    original.longitude,
    70,
    26,
  );
  assert.ok(Math.abs(resized[1].latitude - expected.latitude) < 1e-9);
  assert.ok(Math.abs(resized[1].longitude - expected.longitude) < 1e-9);
  const moved = shapeCoordinates({
    ...edited,
    latitude: original.latitude + 0.001,
  });
  assert.ok(Math.abs(moved[1].latitude - target.latitude - 0.001) < 1e-8);
  assert.throws(() => moveShapePoint(original, -1, 0, 0));
  assert.throws(() => moveShapePoint(original, 4, 0, 0));
  assert.throws(() => moveShapePoint(original, 1, NaN, 0));
});

test("point dragging across the date line uses the nearest local offset", () => {
  const original = { ...base("line"), longitude: 179.99999 };
  const target = offsetCoordinates(
    original.latitude,
    original.longitude,
    15,
    40,
  );
  const edited = moveShapePoint(original, 1, target.latitude, target.longitude);
  assert.ok(Math.abs(edited.vertexOffsets![1][1] - 2) < 1e-5);
  assert.ok(
    Math.abs(shapeCoordinates(edited)[1].longitude - target.longitude) < 1e-9,
  );
});
