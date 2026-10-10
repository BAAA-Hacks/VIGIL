import type { Detection } from "../../types/vigil";

export function DetectionOverlay({ detection }: { detection: Detection }) {
  const [left, top, right, bottom] = detection.bbox_xyxy_norm;
  return (
    <div
      className="absolute border-[1.5px] border-[color:var(--color-pink)]"
      style={{
        left: left * 100 + "%",
        top: top * 100 + "%",
        width: (right - left) * 100 + "%",
        height: (bottom - top) * 100 + "%",
      }}
    >
      <span className="absolute -left-0.5 -top-6 whitespace-nowrap bg-[var(--color-yellow)] px-[7px] py-[5px] text-[10px] font-bold text-[color:var(--color-ink)]">
        {detection.class} · {Math.round(detection.confidence * 100)}%
      </span>
      <i className="absolute -left-[3px] -top-[3px] size-[9px] border-l-[3px] border-t-[3px] border-[color:var(--color-pink)]" />
      <b className="absolute -bottom-[3px] -right-[3px] size-[9px] border-b-[3px] border-r-[3px] border-[color:var(--color-pink)]" />
    </div>
  );
}
