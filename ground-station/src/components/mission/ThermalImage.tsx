"use client";
import { useEffect, useRef } from "react";
import { Radio } from "lucide-react";
import type {
  DetectionResult,
  ThermalFrame,
  ThermalPalette,
} from "../../types/vigil";
import { drawThermalScene } from "../../lib/thermalSimulation";
import { DetectionOverlay } from "./DetectionOverlay";
interface ThermalImageProps {
  frame: ThermalFrame | null;
  detection: DetectionResult | null;
  demo: boolean;
  palette: ThermalPalette;
  hasPerson: boolean;
  presentation?: "panel" | "viewer" | "preview";
  expanded?: boolean;
}
export function ThermalImage({
  frame,
  detection,
  demo,
  palette,
  hasPerson,
  presentation = "panel",
  expanded = false,
}: ThermalImageProps) {
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    if (demo && canvas.current)
      drawThermalScene(canvas.current, palette, hasPerson);
  }, [demo, palette, hasPerson]);
  return (
    <div
      className={`relative overflow-hidden bg-[var(--color-ink)] ${
        presentation === "viewer"
          ? "size-full [container-type:size]"
          : presentation === "preview"
            ? "w-full aspect-[4/3]"
            : expanded
              ? "mx-auto h-[65vh] max-h-[65vh] w-auto aspect-[4/3]"
              : "mx-5 aspect-[4/3] min-[1500px]:mx-auto min-[1500px]:max-h-[510px] min-[1500px]:w-[680px] min-[1500px]:max-w-[calc(100%-40px)] max-[550px]:mx-3"
      }`}
    >
      {/* The boxes are positioned in % of this element, so it must be exactly the 4:3 image:
          one width rule only (a competing w-full would stretch it to the screen's shape). */}
      <div
        className={
          presentation === "viewer"
            ? "absolute left-1/2 top-1/2 aspect-[4/3] -translate-x-1/2 -translate-y-1/2 [width:min(100%,calc(100cqh*4/3))]"
            : "size-full"
        }
      >
        {demo ? (
          <canvas
            className={`block size-full [image-rendering:pixelated] ${presentation === "viewer" ? "object-contain" : "object-fill"}`}
            ref={canvas}
            width={320}
            height={240}
            aria-label={
              hasPerson
                ? "Simulated thermal scene containing one person"
                : "Simulated thermal scene without a person"
            }
          />
        ) : frame?.payload ? (
          <img
            className={`block size-full [image-rendering:pixelated] ${presentation === "viewer" ? "object-contain" : "object-fill"}`}
            src={frame.payload}
            alt="Incoming thermal frame"
          />
        ) : (
          <div className=" h-full flex flex-col items-center justify-center text-[color:var(--color-paper)]/80 [&_h3]:text-[18px]">
            <Radio size={40} />
            <h3>Waiting for thermal frames</h3>
            <p className="text-xs leading-relaxed text-[color:var(--color-paper)]/80">
              Connect your camera feed to begin.
            </p>
          </div>
        )}
        {detection?.detections.map((item, index) => (
          <DetectionOverlay key={index} detection={item} />
        ))}
      </div>
      {presentation === "panel" && (
        <div className=" absolute left-1/2 top-1/2 w-[14px] h-[14px] border-l border-[color:var(--color-paper)]/30 border-t border-[color:var(--color-paper)]/30 -translate-x-1/2 -translate-y-1/2" />
      )}
      {presentation === "panel" && (
        <span className=" absolute bottom-0 left-0 right-0 p-3 [background:linear-gradient(transparent,_color-mix(in_srgb,_var(--color-ink)_75%,_transparent))] text-[8px] tracking-[1px] text-[color:var(--color-paper)] [&_span]:float-right [&_span]:text-[color:var(--color-paper)]/80">
          THERMAL CAMERA <span>TOP-LEFT ORIGIN</span>
        </span>
      )}
    </div>
  );
}
