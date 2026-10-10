import data from "../data/fixture.ts";
import { isDetectionResult, isThermalFrame } from "./validation.ts";
import { isVehicleTelemetry } from "./vehicleTelemetry.ts";
import type { LocationConfig } from "./geolocation.ts";

export const PIN_TEST_CONFIG: LocationConfig = {
  ...data.pin_test.location_config,
  altitudeReference: "absolute",
};

/** Same input contracts as ELRS telemetry and Wi-Fi thermal/detection events. */
export function createPinTestSample(timestamp: number, payload: string) {
  const telemetry = {
    ...data.pin_test.telemetry,
    timestamp_ms: timestamp,
    data_age_ms: 0,
  };
  const frame_id = `pin-test-${timestamp}`;
  const frame = {
    ...data.pin_test.frame,
    frame_id,
    timestamp_ms: timestamp,
    payload,
  };
  const detection = { ...data.pin_test.detection, frame_id };
  if (
    !isVehicleTelemetry(telemetry) ||
    !isThermalFrame(frame) ||
    !isDetectionResult(detection)
  )
    throw new Error("Invalid pin-test inputs in the demo fixture");
  return { telemetry, frame, detection };
}

/** Sensor-image pixels, independent of the UI palette. Heat silhouettes fit the supplied boxes. */
export function pinTestPixels(): Uint8ClampedArray<ArrayBuffer> {
  const width = data.pin_test.frame.width,
    height = data.pin_test.frame.height;
  const pixels = new Uint8ClampedArray(width * height * 4);
  for (let y = 0; y < height; y++)
    for (let x = 0; x < width; x++) {
      let value = 35 + ((x * 7 + y * 11) % 19);
      for (const detection of data.pin_test.detection.detections) {
        const [left, top, right, bottom] = detection.bbox_xyxy_norm;
        const nx = (x / width - left) / (right - left),
          ny = (y / height - top) / (bottom - top);
        const head = ((nx - 0.5) / 0.18) ** 2 + ((ny - 0.14) / 0.14) ** 2 <= 1;
        const torso = nx > 0.2 && nx < 0.8 && ny > 0.28 && ny < 0.66;
        const legs =
          ny >= 0.66 &&
          ny < 1 &&
          ((nx > 0.25 && nx < 0.44) || (nx > 0.56 && nx < 0.75));
        if (head || torso || legs)
          value = Math.round(175 + (detection.temperature_c - 33) * 10);
      }
      const i = (y * width + x) * 4;
      pixels[i] = pixels[i + 1] = pixels[i + 2] = value;
      pixels[i + 3] = 255;
    }
  return pixels;
}
