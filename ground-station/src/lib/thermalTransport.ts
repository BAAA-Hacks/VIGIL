import type {
  Detection,
  DetectionResult,
  ThermalFrame,
} from "../types/vigil.ts";
import { isDetectionResult } from "./validation.ts";

const record = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);
const finite = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value);
const unit = (value: unknown): value is number =>
  finite(value) && value >= 0 && value <= 1;
function envelope(
  value: unknown,
): value is Record<string, unknown> & {
  frame_id: string;
  capture_timestamp_ms: number;
} {
  return (
    record(value) &&
    typeof value.frame_id === "string" &&
    value.frame_id.length > 0 &&
    value.frame_id.length <= 256 &&
    Number.isSafeInteger(value.capture_timestamp_ms) &&
    (value.capture_timestamp_ms as number) >= 0
  );
}

/** Converts the Lepton producer contract into the dashboard contract. */
export function thermalFrame(value: unknown): ThermalFrame | null {
  if (
    !envelope(value) ||
    value.width !== 160 ||
    value.height !== 120 ||
    typeof value.image_data_url !== "string" ||
    value.image_data_url.length > 1_000_000 ||
    !/^data:image\/png;base64,[A-Za-z0-9+/]+={0,2}$/.test(value.image_data_url)
  )
    return null;
  return {
    frame_id: value.frame_id,
    timestamp_ms: value.capture_timestamp_ms,
    width: 160,
    height: 120,
    pixel_format: "encoded-image",
    payload: value.image_data_url,
  };
}

export function thermalDetections(
  value: unknown,
): (DetectionResult & { timestamp_ms: number }) | null {
  if (
    !envelope(value) ||
    !finite(value.processing_ms) ||
    value.processing_ms < 0 ||
    !Array.isArray(value.persons) ||
    value.persons.length > 128
  )
    return null;
  const detections: Detection[] = [];
  for (const person of value.persons) {
    if (
      !record(person) ||
      person.class !== "person" ||
      !Array.isArray(person.bbox) ||
      person.bbox.length !== 4 ||
      !person.bbox.every(unit) ||
      person.bbox[2] <= person.bbox[0] ||
      person.bbox[3] <= person.bbox[1] ||
      !unit(person.confidence) ||
      typeof person.feet_visible !== "boolean" ||
      (person.tracking_id !== null &&
        (!Number.isSafeInteger(person.tracking_id) ||
          (person.tracking_id as number) < 0)) ||
      (person.center_temperature_c !== null &&
        !finite(person.center_temperature_c))
    )
      continue;
    const [left, , right, bottom] = person.bbox;
    // Current projection uses the box's bottom midpoint. Reject inconsistent foot coordinates.
    if (
      !Array.isArray(person.bottom_center) ||
      person.bottom_center.length !== 2 ||
      !person.bottom_center.every(unit) ||
      Math.abs(person.bottom_center[0] - (left + right) / 2) > 0.001 ||
      Math.abs(person.bottom_center[1] - bottom) > 0.001
    )
      continue;
    const detection: Detection = {
      class: "person",
      confidence: person.confidence,
      bbox_xyxy_norm: [
        person.bbox[0],
        person.bbox[1],
        person.bbox[2],
        person.bbox[3],
      ],
      feet_visible: person.feet_visible && bottom < 1,
      ...(person.tracking_id !== null && {
        track_id: String(person.tracking_id),
      }),
      ...(person.center_temperature_c !== null && {
        temperature_c: person.center_temperature_c as number,
      }),
    };
    if (
      isDetectionResult({
        frame_id: value.frame_id,
        processing_ms: value.processing_ms,
        detections: [detection],
      })
    )
      detections.push(detection);
  }
  return {
    frame_id: value.frame_id,
    timestamp_ms: value.capture_timestamp_ms,
    processing_ms: value.processing_ms,
    detections,
  };
}

/** Bounded pairing buffer, allowing either event order without mismatched overlays. */
export class ThermalPairs {
  private frames = new Map<string, ThermalFrame>();
  private results = new Map<
    string,
    DetectionResult & { timestamp_ms: number }
  >();
  private lastTimestamp = -1;
  private lastId = "";
  push(
    kind: "frame" | "detection",
    raw: unknown,
  ): { frame: ThermalFrame; detection: DetectionResult } | null {
    if (kind === "frame") {
      const frame = thermalFrame(raw);
      if (!frame) return null;
      this.frames.set(frame.frame_id, frame);
    } else {
      const detection = thermalDetections(raw);
      if (!detection) return null;
      this.results.set(detection.frame_id, detection);
    }
    for (const map of [this.frames, this.results]) {
      while (map.size > 32) map.delete(map.keys().next().value!);
    }
    if (!envelope(raw)) return null;
    const frame = this.frames.get(raw.frame_id),
      detection = this.results.get(raw.frame_id);
    if (!frame || !detection) return null;
    this.frames.delete(raw.frame_id);
    this.results.delete(raw.frame_id);
    if (
      frame.timestamp_ms !== detection.timestamp_ms ||
      frame.timestamp_ms < this.lastTimestamp ||
      (frame.timestamp_ms === this.lastTimestamp &&
        frame.frame_id === this.lastId)
    )
      return null;
    this.lastTimestamp = frame.timestamp_ms;
    this.lastId = frame.frame_id;
    return { frame, detection };
  }
  reset() {
    this.frames.clear();
    this.results.clear();
    this.lastTimestamp = -1;
    this.lastId = "";
  }
}
