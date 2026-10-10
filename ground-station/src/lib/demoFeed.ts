import type {
  BoundingBox,
  DemoScenario,
  DetectionResult,
  ThermalFrame,
} from "../types/vigil";
const HUMAN_BOX: BoundingBox = [0.43, 0.28, 0.56, 0.79];
export function createDemoSample(
  scenario: DemoScenario,
  timestamp: number,
): { frame: ThermalFrame; detection: DetectionResult } {
  const frameId = `demo-${timestamp}`;
  return {
    frame: {
      frame_id: frameId,
      timestamp_ms: timestamp,
      width: 320,
      height: 240,
    },
    detection: {
      frame_id: frameId,
      processing_ms: 38,
      detections:
        scenario === "human"
          ? [
              {
                class: "Human",
                confidence: 0.947,
                bbox_xyxy_norm: [...HUMAN_BOX],
              },
            ]
          : [],
    },
  };
}
