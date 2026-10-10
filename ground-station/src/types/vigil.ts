export type FeedMode = "demo" | "live";
export type DemoScenario = "human" | "empty" | "disconnected";
export type ThermalPalette = "iron" | "white";
export type BoundingBox = [number, number, number, number];
export interface ThermalFrame {
  frame_id: string;
  timestamp_ms: number;
  width: number;
  height: number;
  pixel_format?: string;
  payload?: string;
}
export interface Detection {
  class: string;
  confidence: number;
  bbox_xyxy_norm: BoundingBox;
}
export interface DetectionResult {
  frame_id: string;
  processing_ms: number;
  detections: Detection[];
}
