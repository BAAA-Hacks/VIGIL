import type { Detection } from "../../types/vigil";
export function DetectionOverlay({ detection }: { detection: Detection }) {
  return (
    <div
      className="bounding"
      style={{
        left: `${detection.bbox_xyxy_norm[0] * 100}%`,
        top: `${detection.bbox_xyxy_norm[1] * 100}%`,
        width: `${(detection.bbox_xyxy_norm[2] - detection.bbox_xyxy_norm[0]) * 100}%`,
        height: `${(detection.bbox_xyxy_norm[3] - detection.bbox_xyxy_norm[1]) * 100}%`,
      }}
    >
      <span>
        {detection.class} · {Math.round(detection.confidence * 100)}%
      </span>
      <i />
      <b />
    </div>
  );
}
