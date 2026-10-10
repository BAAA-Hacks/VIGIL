import { test } from "node:test";
import assert from "node:assert/strict";
import { isDetectionResult, isThermalFrame } from "../src/lib/validation.ts";
import { drawThermalScene } from "../src/lib/thermalSimulation.ts";

const sample = {
  frame: { frame_id: "f-1", timestamp_ms: 10_000, width: 160, height: 120 },
  detection: {
    frame_id: "f-1",
    processing_ms: 38,
    detections: [
      {
        class: "person",
        confidence: 0.95,
        bbox_xyxy_norm: [0.4, 0.3, 0.6, 0.8],
      },
    ],
  },
};
test("a well-formed detection result is accepted", () => {
  assert.equal(isDetectionResult(sample.detection), true);
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
