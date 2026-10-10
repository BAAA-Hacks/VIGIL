"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import type { VehicleTelemetry } from "../types/telemetry";
import type { DetectionResult, ThermalFrame } from "../types/vigil";
import { isVehicleTelemetry } from "../lib/vehicleTelemetry";
import { isDetectionResult, isThermalFrame } from "../lib/validation";
import {
  CourseHeading,
  type LocationConfig,
  type Terrain,
} from "../lib/geolocation";

import { gridTerrain, type TerrainGrid } from "../lib/terrainGrid";
import { isLocationConfig } from "../lib/locationConfig";
import { VIGIL_EVENTS } from "../lib/events";
import { locationSnapshot, LOCATION_STALE_MS } from "../lib/locationSnapshot";

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
    let expiry: ReturnType<typeof setTimeout> | undefined;
    // Wake only when a received input expires. No polling while idle or stale.
    const scheduleExpiry = () => {
      clearTimeout(expiry);
      const time = Date.now();
      const deadlines = [received.current, telemetryReceived.current]
        .filter((arrival) => arrival > 0)
        .map((arrival) => arrival + LOCATION_STALE_MS + 1)
        .filter((deadline) => deadline > time);
      if (deadlines.length)
        expiry = setTimeout(
          () => {
            setNow(Date.now());
            scheduleExpiry();
          },
          Math.min(...deadlines) - time,
        );
    };
    const ingest = (t: VehicleTelemetry) => {
      if (t.timestamp_ms <= lastTime.current) return;
      if (lastTime.current && t.timestamp_ms - lastTime.current > 2000)
        calibrator.current.reset();
      lastTime.current = t.timestamp_ms;
      telemetryReceived.current = Date.now();
      setNow(telemetryReceived.current);
      scheduleExpiry();
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
      scheduleExpiry();
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
    scheduleExpiry();
    window.addEventListener(VIGIL_EVENTS.terrain, terrainEvent);
    window.addEventListener(VIGIL_EVENTS.telemetry, telemetry);
    window.addEventListener(VIGIL_EVENTS.frame, frame);
    window.addEventListener(VIGIL_EVENTS.detection, detections);
    window.addEventListener(VIGIL_EVENTS.locationConfig, configuration);
    return () => {
      clearTimeout(expiry);
      window.removeEventListener(VIGIL_EVENTS.terrain, terrainEvent);
      window.removeEventListener(VIGIL_EVENTS.telemetry, telemetry);
      window.removeEventListener(VIGIL_EVENTS.frame, frame);
      window.removeEventListener(VIGIL_EVENTS.detection, detections);
      window.removeEventListener(VIGIL_EVENTS.locationConfig, configuration);
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
  return useMemo(
    () =>
      locationSnapshot({
        active,
        frames,
        detection,
        config: projectionConfig,
        history,
        now,
        frameReceived: received.current,
        telemetryReceived: telemetryReceived.current,
        terrain,
        testing: testConfig !== null,
        headingFor: (telemetry) => calibrator.current.heading(telemetry),
      }),
    [
      active,
      frames,
      detection,
      projectionConfig,
      history,
      now,
      terrain,
      testConfig,
    ],
  );
}
