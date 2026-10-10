"use client";
import { useEffect, useRef, useState } from "react";
import {
  createPathMission,
  missionXml,
  SHAPE_POINTS,
  type PathShape,
  type PathShapeKind,
  type PathMission,
} from "../lib/missionPath";

export function useMissionPlanner() {
  const [shapes, setShapes] = useState<PathShape[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [altitude, setAltitude] = useState("10");
  const [speed, setSpeed] = useState("2");
  const [reference, setReference] =
    useState<PathMission["altitudeReference"]>("home");
  const [takeoverConfirmed, setTakeoverConfirmed] = useState(false);
  const [sending, setSending] = useState(false);
  const [message, setMessage] = useState("");
  const [configured, setConfigured] = useState(false);
  const request = useRef<AbortController | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/mission", { signal: controller.signal })
      .then((r) => r.json())
      .then((data) => {
        setConfigured(data.configured === true);
        if (!data.configured)
          setMessage(
            "Upload connection not configured. XML export is available.",
          );
      })
      .catch(() => {
        if (!controller.signal.aborted)
          setMessage(
            "Mission connection unavailable. XML export is available.",
          );
      });
    return () => {
      controller.abort();
      request.current?.abort();
    };
  }, []);
  const count = shapes.reduce((total, s) => total + SHAPE_POINTS[s.kind], 0);
  function add(
    kind: PathShapeKind,
    latitude: number,
    longitude: number,
    sizeM = 20,
  ) {
    if (sending) return;
    if (count + SHAPE_POINTS[kind] > 60) {
      setMessage("A route can contain at most 60 points.");
      return;
    }
    const shape = {
      id: crypto.randomUUID(),
      kind,
      latitude,
      longitude,
      sizeM: Math.max(2, Math.min(500, sizeM)),
    };
    setShapes((old) => [...old, shape]);
    setSelectedId(shape.id);
    setMessage("Route edited · upload when ready");
  }
  function update(shape: PathShape) {
    if (sending) return;
    setShapes((old) => old.map((s) => (s.id === shape.id ? shape : s)));
    setMessage("Route edited · upload when ready");
  }
  function remove() {
    if (sending) return;
    setShapes((old) => old.filter((s) => s.id !== selectedId));
    setSelectedId(null);
    setMessage("Route edited · upload when ready");
  }
  function mission() {
    return createPathMission(
      shapes,
      Number(altitude),
      Number(speed),
      reference,
    );
  }
  function exportXml() {
    try {
      const url = URL.createObjectURL(
        new Blob([missionXml(mission())], { type: "application/xml" }),
      );
      const link = document.createElement("a");
      link.href = url;
      link.download = "vigil-mission.xml";
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Invalid route");
    }
  }
  async function send() {
    if (sending || !takeoverConfirmed) return;
    try {
      const route = mission();
      setSending(true);
      setMessage("Uploading and verifying waypoints…");
      const controller = new AbortController();
      request.current = controller;
      const response = await fetch("/api/mission", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mission: route, takeoverConfirmed }),
        signal: controller.signal,
      });
      const result = await response.json();
      if (!response.ok || !result.verified)
        throw new Error(result.error || "Upload was not verified");
      setMessage(
        `Verified ${result.waypoints} points · use transmitter NAV WP to start · finish holds position`,
      );
    } catch (error) {
      if (!request.current?.signal.aborted)
        setMessage(error instanceof Error ? error.message : "Upload failed");
    } finally {
      setSending(false);
      request.current = null;
    }
  }
  return {
    shapes,
    selectedId,
    select: setSelectedId,
    selected: shapes.find((s) => s.id === selectedId) ?? null,
    count,
    add,
    update,
    remove,
    altitude,
    setAltitude: (value: string) => {
      setAltitude(value);
      setMessage("Route edited · upload when ready");
    },
    speed,
    setSpeed: (value: string) => {
      setSpeed(value);
      setMessage("Route edited · upload when ready");
    },
    reference,
    setReference: (value: PathMission["altitudeReference"]) => {
      setReference(value);
      setMessage("Route edited · upload when ready");
    },
    takeoverConfirmed,
    setTakeoverConfirmed,
    configured,
    sending,
    message,
    exportXml,
    send,
  };
}
