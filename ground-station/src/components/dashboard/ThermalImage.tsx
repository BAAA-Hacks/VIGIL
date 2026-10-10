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
}
export function ThermalImage({
  frame,
  detection,
  demo,
  palette,
  hasPerson,
}: ThermalImageProps) {
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    if (demo && canvas.current)
      drawThermalScene(canvas.current, palette, hasPerson);
  }, [demo, palette, hasPerson]);
  return (
    <div className="image-area">
      {demo ? (
        <canvas
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
        <img src={frame.payload} alt="Incoming thermal frame" />
      ) : (
        <div className="empty">
          <Radio size={40} />
          <h3>Waiting for thermal frames</h3>
          <p>Connect your camera feed to begin.</p>
        </div>
      )}
      {detection?.detections.map((item, index) => (
        <DetectionOverlay key={index} detection={item} />
      ))}
      <div className="crosshair" />
      <span className="image-caption">
        {demo ? "SIMULATED THERMAL IMAGE" : "THERMAL CAMERA"}{" "}
        <span>TOP-LEFT ORIGIN</span>
      </span>
    </div>
  );
}
