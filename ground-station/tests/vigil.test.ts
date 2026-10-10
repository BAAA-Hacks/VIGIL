import { test } from "node:test";
import assert from "node:assert/strict";
import { createDemoSample } from "../src/lib/demoFeed.ts";
import { deriveFeedStatus } from "../src/lib/feedStatus.ts";
import { isDetectionResult, isThermalFrame } from "../src/lib/validation.ts";
import { drawThermalScene } from "../src/lib/thermalSimulation.ts";

const sample = createDemoSample("human", 10_000);
const snapshot = {
  ...sample,
  now: 10_100,
  received: 10_000,
  demo: true,
  paused: false,
  scenario: "human" as const,
};
test("demo detections match their frame, and empty scenes have no detections", () => {
  assert.equal(sample.frame.frame_id, sample.detection.frame_id);
  assert.equal(isDetectionResult(sample.detection), true);
  assert.equal(
    createDemoSample("empty", 10_000).detection.detections.length,
    0,
  );
});
test("only fresh detections with the displayed frame ID are exposed", () => {
  assert.equal(deriveFeedStatus(snapshot).humans.length, 1);
  assert.equal(
    deriveFeedStatus({
      ...snapshot,
      detection: { ...sample.detection, frame_id: "other" },
    }).current,
    null,
  );
  assert.equal(deriveFeedStatus({ ...snapshot, now: 12_001 }).current, null);
});
test("feed status distinguishes pause, stale, disconnected, and live", () => {
  assert.equal(
    deriveFeedStatus({ ...snapshot, paused: true }).status,
    "Paused",
  );
  assert.equal(
    deriveFeedStatus({ ...snapshot, now: 12_001 }).status,
    "Feed stale",
  );
  assert.equal(
    deriveFeedStatus({ ...snapshot, now: 15_001 }).status,
    "Disconnected",
  );
  assert.equal(
    deriveFeedStatus({ ...snapshot, demo: false }).status,
    "Live feed",
  );
});
test("external validation rejects malformed and inverted boxes and invalid frame dimensions", () => {
  for (const box of [
    [0, 0, 2, 1],
    [0.8, 0, 0.2, 1],
    [0, 0, NaN, 1],
    [0, 1],
  ]) {
    assert.equal(
      isDetectionResult({
        ...sample.detection,
        detections: [
          { ...sample.detection.detections[0], bbox_xyxy_norm: box },
        ],
      }),
      false,
    );
  }
  const live = { ...sample.frame, payload: "data:image/png;base64,example" };
  assert.equal(isThermalFrame(live), true);
  assert.equal(isThermalFrame({ ...live, width: 0 }), false);
  assert.equal(
    isThermalFrame({ ...live, payload: "https://example.com/image.png" }),
    false,
  );
});
test("thermal simulation is reproducible and changes with person visibility and palette", () => {
  function render(hasPerson: boolean, palette: "iron" | "white") {
    let result: Uint8ClampedArray = new Uint8ClampedArray();
    const context = {
      createImageData: (width: number, height: number) => ({
        data: new Uint8ClampedArray(width * height * 4),
      }),
      putImageData: (image: { data: Uint8ClampedArray }) => {
        result = image.data;
      },
    };
    const canvas = {
      getContext: () => context,
    } as unknown as HTMLCanvasElement;
    drawThermalScene(canvas, palette, hasPerson);
    return result;
  }
  const person = render(true, "iron");
  assert.equal(person.length, 320 * 240 * 4);
  assert.deepEqual(person, render(true, "iron"));
  assert.notDeepEqual(person, render(false, "iron"));
  assert.notDeepEqual(person, render(true, "white"));
});
