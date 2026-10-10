"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import type { VehicleTelemetry } from "../types/telemetry";
import type { DetectionResult, ThermalFrame } from "../types/vigil";
import type { PinData } from "../types/mission";
import { isVehicleTelemetry } from "../lib/vehicleTelemetry";
import { isDetectionResult, isThermalFrame } from "../lib/validation";
import {
  CourseHeading,
  projectPerson,
  telemetryAt,
  wrap,
  type LocationConfig,
  type Terrain,
} from "../lib/geolocation";

import { gridTerrain, type TerrainGrid } from "../lib/terrainGrid";

export function isLocationConfig(value: unknown): value is LocationConfig {
  if (!value || typeof value !== "object") return false;
  const c = value as Record<string, unknown>;
  const finite = (key: string) =>
    typeof c[key] === "number" && Number.isFinite(c[key]);
  return (
    (c.altitudeReference === "takeoff" || c.altitudeReference === "absolute") &&
    finite("startingCameraHeightM") &&
    finite("mountDownDeg") &&
    finite("frameClockOffsetMs") &&
    typeof c.nativeImageConfirmed === "boolean" &&
    typeof c.attitudeConventionConfirmed === "boolean" &&
    typeof c.forwardFlightConfirmed === "boolean" &&
    ["takeoffElevationM", "headingOffsetDeg", "fx", "fy", "cx", "cy"].every(
      (k) => c[k] === undefined || finite(k),
    )
  );
}

/** Live transport adapter. Capture timestamps and session conventions are explicit inputs. */
export function usePersonLocations(
  latest: VehicleTelemetry | null,
  testConfig: LocationConfig | null = null,
) {
  const [history, setHistory] = useState<VehicleTelemetry[]>([]);
  const [frames, setFrames] = useState<ThermalFrame[]>([]);
  const [detection, setDetection] = useState<DetectionResult | null>(null);
  const [config, setConfig] = useState<LocationConfig | null>(null);
  const projectionConfig = testConfig ?? config;
  const [terrain, setTerrain] = useState<Terrain | undefined>();
  const [active, setActive] = useState(false);
  const [now, setNow] = useState(0);
  const received = useRef(0);
  const telemetryReceived = useRef(0);
  const calibrator = useRef(new CourseHeading());
  const lastTime = useRef(0);
  const ingestRef = useRef<(t: VehicleTelemetry) => void>(() => {});
  useEffect(() => {
    const ingest = (t: VehicleTelemetry) => {
      if (t.timestamp_ms <= lastTime.current) return;
      if (lastTime.current && t.timestamp_ms - lastTime.current > 2000)
        calibrator.current.reset();
      lastTime.current = t.timestamp_ms;
      telemetryReceived.current = Date.now();
      calibrator.current.observe(
        t,
        projectionConfig?.forwardFlightConfirmed ?? false,
      );
      setHistory((h) =>
        [...h.filter((p) => t.timestamp_ms - p.timestamp_ms <= 30000), t].slice(
          -600,
        ),
      );
    };
    ingestRef.current = ingest;
    const telemetry = (e: Event) => {
      if (e instanceof CustomEvent && isVehicleTelemetry(e.detail))
        ingest(e.detail);
    };
    const frame = (e: Event) => {
      if (!(e instanceof CustomEvent) || !isThermalFrame(e.detail)) return;
      const f = e.detail;
      setFrames((old) =>
        [...old.filter((p) => p.frame_id !== f.frame_id), f].slice(-32),
      );
      setActive(true);
      received.current = Date.now();
      setNow(Date.now());
    };
    const detections = (e: Event) => {
      if (e instanceof CustomEvent && isDetectionResult(e.detail))
        setDetection(e.detail);
    };
    const configuration = (e: Event) => {
      if (!(e instanceof CustomEvent) || !isLocationConfig(e.detail)) return;
      calibrator.current.reset();
      lastTime.current = 0;
      setHistory([]);
      setFrames([]);
      setDetection(null);
      setTerrain(undefined);
      setConfig(e.detail);
    };
    const terrainEvent = (e: Event) => {
      if (!(e instanceof CustomEvent)) return;
      if (e.detail === null) {
        setTerrain(undefined);
        return;
      }
      try {
        const grid = e.detail as TerrainGrid;
        if (
          !Array.isArray(grid.elevations) ||
          grid.elevations.length > 512 ||
          grid.elevations.some((row) => !Array.isArray(row) || row.length > 512)
        )
          return;
        const sampler = gridTerrain(grid);
        setTerrain(() => sampler);
      } catch {
        /* Invalid or incomplete surfaces are not installed. */
      }
    };
    const timer = setInterval(() => setNow(Date.now()), 250);
    window.addEventListener("vigil:terrain", terrainEvent);
    window.addEventListener("vigil:telemetry", telemetry);
    window.addEventListener("vigil:frame", frame);
    window.addEventListener("vigil:detection", detections);
    window.addEventListener("vigil:location-config", configuration);
    return () => {
      clearInterval(timer);
      window.removeEventListener("vigil:terrain", terrainEvent);
      window.removeEventListener("vigil:telemetry", telemetry);
      window.removeEventListener("vigil:frame", frame);
      window.removeEventListener("vigil:detection", detections);
      window.removeEventListener("vigil:location-config", configuration);
    };
  }, [projectionConfig]);
  useEffect(() => {
    calibrator.current.reset();
    lastTime.current = 0;
    setHistory([]);
    setFrames([]);
    setDetection(null);
    setActive(false);
    received.current = 0;
    telemetryReceived.current = 0;
  }, [testConfig]);
  useEffect(() => {
    if (latest) ingestRef.current(latest);
  }, [latest]);
  return useMemo(() => {
    const frame = detection
      ? (frames.find((f) => f.frame_id === detection.frame_id) ?? null)
      : (frames.at(-1) ?? null);
    const current = frame?.frame_id === detection?.frame_id ? detection : null;
    const pins: PinData[] = [],
      reasons: string[] = [];
    const base = {
      active,
      frame,
      detection: current,
      pins,
      reasons,
      telemetry: history.at(-1) ?? null,
      drone:
        now - telemetryReceived.current <= 2000
          ? (history.at(-1) ?? null)
          : null,
    };
    if (!active) return { ...base, message: "" };
    if (now - received.current > 2000)
      return {
        ...base,
        detection: null,
        message: "Thermal feed stale · locations withheld",
      };
    if (!projectionConfig)
      return {
        ...base,
        message:
          "Location setup required: altitude, heading and camera conventions",
      };
    if (!frame || !current)
      return { ...base, message: "Waiting for matching frame and detections" };
    if (frame.width !== 160 || frame.height !== 120)
      return {
        ...base,
        message: "Projection requires the native 160 × 120 image",
      };
    if (now - telemetryReceived.current > 2000)
      return { ...base, message: "Telemetry stale · locations withheld" };
    const capture = frame.timestamp_ms + projectionConfig.frameClockOffsetMs;
    const t = telemetryAt(history, capture);
    if (!t || Math.abs((history.at(-1)?.timestamp_ms ?? 0) - capture) > 2000)
      return { ...base, message: "Waiting for synchronized GPS and attitude" };
    const heading =
      t.yaw_deg !== null && projectionConfig.headingOffsetDeg !== undefined
        ? wrap(t.yaw_deg + projectionConfig.headingOffsetDeg)
        : calibrator.current.heading(t);
    current.detections
      .filter((d) => d.class === "person" || d.class === "human")
      .forEach((d, index) => {
        const result =
          d.feet_visible === false
            ? { available: false as const, reason: "Feet obscured" }
            : projectPerson(
                d.bbox_xyxy_norm,
                t,
                heading,
                projectionConfig,
                testConfig ? undefined : terrain,
              );
        if (!result.available) {
          reasons.push(`Detection ${index + 1}: ${result.reason}`);
          return;
        }
        const id = d.track_id ?? `${frame.frame_id}:${index}`;
        pins.push({
          id,
          displayLabel: String(index + 1),
          name: d.track_id ? `Person ${d.track_id}` : `Detection ${index + 1}`,
          latitude: result.latitude,
          longitude: result.longitude,
          coords: `${result.latitude.toFixed(6)}, ${result.longitude.toFixed(6)}`,
          temp:
            d.temperature_c === undefined
              ? "Unavailable"
              : `${d.temperature_c.toFixed(1)} °C`,
          status: d.temperature_status ?? "unknown",
          locationNote: `${result.method} · provisional optics / heading`,
          capturedAt: capture,
          ...(testConfig
            ? { groundElevationM: projectionConfig.takeoffElevationM }
            : {}),
        });
      });
    return {
      ...base,
      message: pins.length
        ? terrain && !testConfig
          ? "Estimated coordinates · local terrain"
          : "Estimated coordinates · flat reference ground"
        : reasons.length
          ? "Locations unavailable"
          : "No people detected",
    };
  }, [
    active,
    frames,
    detection,
    projectionConfig,
    history,
    now,
    terrain,
    testConfig,
  ]);
}
