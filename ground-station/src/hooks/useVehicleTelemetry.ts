"use client";
import { useEffect, useRef, useState } from "react";
import type { VehicleTelemetry } from "../types/telemetry";
import { isVehicleTelemetry } from "../lib/vehicleTelemetry";
const PACKET_TIMEOUT_MS = 2000;
export function useVehicleTelemetry() {
  const [enabled, setEnabled] = useState(false);
  const [data, setData] = useState<VehicleTelemetry | null>(null);
  const [state, setState] = useState("Stopped");
  const [received, setReceived] = useState(0);
  const [now, setNow] = useState(0);
  const [started, setStarted] = useState(0);
  const lastPacket = useRef(0);
  useEffect(() => {
    if (!enabled) return;
    setState("Connecting");
    const stream = new EventSource("/api/telemetry");
    const resetClock = () => {
      lastPacket.current = 0;
      setStarted(0);
    };
    stream.addEventListener("telemetry", (event) => {
      try {
        const value: unknown = JSON.parse((event as MessageEvent).data);
        if (!isVehicleTelemetry(value)) return;
        const arrival = Date.now();
        if (
          !lastPacket.current ||
          arrival - lastPacket.current > PACKET_TIMEOUT_MS
        )
          setStarted(arrival);
        lastPacket.current = arrival;
        setData(value);
        setReceived(arrival);
        setNow(arrival);
        setState("Connected");
      } catch {
        setState("Invalid telemetry");
      }
    });
    stream.addEventListener("bridge-error", () => {
      setState("Bridge unavailable");
      resetClock();
      stream.close();
    });
    stream.onerror = () => {
      setState("Disconnected");
      resetClock();
    };
    const timer = setInterval(() => {
      const current = Date.now();
      setNow(current);
      if (
        lastPacket.current &&
        current - lastPacket.current > PACKET_TIMEOUT_MS
      )
        resetClock();
    }, 250);
    return () => {
      stream.close();
      clearInterval(timer);
      lastPacket.current = 0;
    };
  }, [enabled]);
  const stale =
    enabled &&
    received > 0 &&
    (now - received > PACKET_TIMEOUT_MS ||
      (data?.data_age_ms ?? 0) > PACKET_TIMEOUT_MS ||
      data?.link_state === "lost" ||
      data?.link_state === "no_data");
  const seconds =
    enabled && started && !stale && state === "Connected"
      ? Math.max(0, Math.floor((now - started) / 1000))
      : 0;
  const flightTime = `${Math.floor(seconds / 60)
    .toString()
    .padStart(2, "0")}:${(seconds % 60).toString().padStart(2, "0")}`;
  function toggleTestData() {
    setEnabled((value) => !value);
    setData(null);
    setReceived(0);
    setStarted(0);
    setNow(0);
    lastPacket.current = 0;
    setState(enabled ? "Stopped" : "Connecting");
  }
  return {
    data,
    state: stale ? "Stale" : state,
    stale,
    enabled,
    toggleTestData,
    flightTime,
  };
}
