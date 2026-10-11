import type { DetectionResult, ThermalFrame } from "../../types/vigil";

interface CameraStatusProps {
  frame: ThermalFrame | null;
  detection: DetectionResult | null;
  fps: number | null;
  /** Feed problem from the transport ("Thermal feed disconnected", …); empty when streaming. */
  feedMessage: string;
  replay: boolean;
}

/** One line over the thermal view: is it replay, is the camera streaming, how fast. */
export function CameraStatus({
  frame,
  detection,
  fps,
  feedMessage,
  replay,
}: CameraStatusProps) {
  const parts = [
    feedMessage || (frame ? "Camera streaming" : "Waiting for camera"),
    ...(fps !== null && frame ? [`${fps.toFixed(1)} fps`] : []),
    ...(detection
      ? [`detector ${Math.round(detection.processing_ms)} ms`]
      : []),
    ...(frame?.scene_min_c !== undefined && frame.scene_max_c !== undefined
      ? [
          `scene ${frame.scene_min_c.toFixed(1)}–${frame.scene_max_c.toFixed(1)} °C`,
        ]
      : []),
  ];
  return (
    <div className="pointer-events-none absolute left-2 top-2 z-10 flex flex-wrap items-center gap-1.5 text-[10px]">
      {replay && (
        <span className="rounded-[3px] bg-[var(--color-yellow)] px-1.5 py-0.5 font-bold tracking-[0.5px] text-[color:var(--color-ink)]">
          REPLAY · recorded flight
        </span>
      )}
      <span className="rounded-[3px] bg-[color-mix(in_srgb,var(--color-ink)_70%,transparent)] px-1.5 py-0.5 tabular-nums text-[color:var(--color-paper)]">
        {parts.join(" · ")}
      </span>
    </div>
  );
}
