export type ThermalPalette = "iron" | "white";
export type BoundingBox = [number, number, number, number];
export interface ThermalFrame {
  frame_id: string;
  timestamp_ms: number;
  width: number;
  height: number;
  pixel_format?: string;
  payload?: string;
  /** Coldest / hottest apparent temperature in the frame, when the camera is radiometric. */
  scene_min_c?: number;
  scene_max_c?: number;
}
export interface Detection {
  track_id?: string;
  /** Display name shared with the person's pin, e.g. "Person 2". */
  label?: string;
  feet_visible?: boolean;
  temperature_c?: number;
  temperature_status?: "normal" | "elevated" | "low";
  class: string;
  confidence: number;
  bbox_xyxy_norm: BoundingBox;
}
export interface DetectionResult {
  frame_id: string;
  processing_ms: number;
  detections: Detection[];
}
