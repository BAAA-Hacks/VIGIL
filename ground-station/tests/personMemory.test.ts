import test from "node:test";
import assert from "node:assert/strict";
import { PersonMemory } from "../src/lib/personMemory.ts";
import type { PinData } from "../src/types/mission.ts";

const pin = (id: string, latitude: number, capturedAt: number): PinData => ({
  id,
  name: `Person ${id}`,
  coords: "",
  latitude,
  longitude: 0,
  temp: "",
  status: "unknown",
  capturedAt,
});

test("a person who leaves the view stays at their last position, marked not in view", () => {
  const memory = new PersonMemory();
  memory.update([pin("7", 1, 100)], 100);
  memory.update([pin("7", 2, 200)], 200);
  const [person] = memory.update([], 300);
  assert.equal(person.latitude, 2);
  assert.equal(person.lastSeenAt, 200);
  assert.equal(person.inView, false);
});

test("people keep the number they were found with, in order", () => {
  const memory = new PersonMemory();
  memory.update([pin("40", 0, 1)], 1);
  const pins = memory.update([pin("12", 0, 2), pin("40", 0, 2)], 2);
  assert.deepEqual(
    pins.map((p) => [p.id, p.displayLabel, p.name, p.inView]),
    [
      ["40", "1", "Person 1", true],
      ["12", "2", "Person 2", true],
    ],
  );
});

test("one tracked person is never listed twice", () => {
  const memory = new PersonMemory();
  for (let t = 0; t < 5; t++) memory.update([pin("3", t, t)], t);
  assert.equal(memory.update([pin("3", 9, 9)], 9).length, 1);
});

test("untracked detections are shown only while in view", () => {
  const memory = new PersonMemory();
  assert.equal(memory.update([pin("frame-1:0", 0, 1)], 1).length, 1);
  assert.equal(memory.update([], 2).length, 0);
});

test("slot numbers are reserved on first request", () => {
  const memory = new PersonMemory();
  assert.equal(memory.numberFor("a"), 1);
  assert.equal(memory.numberFor("b"), 2);
  assert.equal(memory.numberFor("a"), 1);
});

const withPhoto = (id: string, capturedAt: number, conf: number): PinData => ({
  ...pin(id, capturedAt, capturedAt),
  review: {
    frame: {
      frame_id: `f${capturedAt}`,
      timestamp_ms: capturedAt,
      width: 160,
      height: 120,
      pixel_format: "encoded-image",
    },
    detection: {
      class: "person",
      confidence: conf,
      bbox_xyxy_norm: [0.1, 0.1, 0.2, 0.5],
    },
  },
});
const photoOf = (pins: PinData[]) => pins[0].review?.frame.frame_id;

test("the photo is the latest clear one, while the position stays live", () => {
  const memory = new PersonMemory();
  memory.update([withPhoto("1", 1, 0.5)], 1);
  assert.equal(photoOf(memory.update([withPhoto("1", 2, 0.4)], 2)), "f1");
  assert.equal(photoOf(memory.update([withPhoto("1", 3, 0.8)], 3)), "f3");
  const pins = memory.update([withPhoto("1", 4, 0.55)], 4);
  assert.equal(photoOf(pins), "f3");
  assert.equal(pins[0].latitude, 4);
  assert.equal(photoOf(memory.update([withPhoto("1", 5, 0.75)], 5)), "f5");
});

test("a detected person stays in view even when no pin could be placed this frame", () => {
  const memory = new PersonMemory();
  memory.update([pin("4", 1, 1)], 1);
  assert.equal(memory.update([], 2, ["4"])[0].inView, true);
  assert.equal(memory.update([], 3)[0].inView, false);
});
