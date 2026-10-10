import type { Detection, DetectionResult, ThermalFrame } from "../types/vigil";
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}
export function isThermalFrame(value: unknown): value is ThermalFrame {
  return (
    isRecord(value) &&
    typeof value.frame_id === "string" &&
    isFiniteNumber(value.timestamp_ms) &&
    isFiniteNumber(value.width) &&
    value.width > 0 &&
    isFiniteNumber(value.height) &&
    value.height > 0 &&
    typeof value.payload === "string" &&
    value.payload.startsWith("data:image/")
  );
}
function isDetection(value: unknown): value is Detection {
  if (
    !isRecord(value) ||
    typeof value.class !== "string" ||
    !isFiniteNumber(value.confidence) ||
    value.confidence < 0 ||
    value.confidence > 1
  )
    return false;
  if (
    (value.track_id !== undefined &&
      (typeof value.track_id !== "string" ||
        !value.track_id.length ||
        value.track_id.length > 64)) ||
    (value.feet_visible !== undefined &&
      typeof value.feet_visible !== "boolean") ||
    (value.temperature_c !== undefined &&
      !isFiniteNumber(value.temperature_c)) ||
    (value.temperature_status !== undefined &&
      !["normal", "low", "elevated"].includes(String(value.temperature_status)))
  )
    return false;
  const box = value.bbox_xyxy_norm;
  return (
    Array.isArray(box) &&
    box.length === 4 &&
    box.every(
      (coordinate: unknown) =>
        isFiniteNumber(coordinate) && coordinate >= 0 && coordinate <= 1,
    ) &&
    box[2] > box[0] &&
    box[3] > box[1]
  );
}
export function isDetectionResult(value: unknown): value is DetectionResult {
  return (
    isRecord(value) &&
    typeof value.frame_id === "string" &&
    isFiniteNumber(value.processing_ms) &&
    value.processing_ms >= 0 &&
    Array.isArray(value.detections) &&
    value.detections.every(isDetection)
  );
}
