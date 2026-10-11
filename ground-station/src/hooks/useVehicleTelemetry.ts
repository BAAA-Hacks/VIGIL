"use client";
import { useEffect, useRef, useState } from "react";
import type { VehicleTelemetry } from "../types/telemetry";
import { isVehicleTelemetry } from "../lib/vehicleTelemetry";
import { formatClock } from "../lib/droneReadings";
const PACKET_TIMEOUT_MS = 2000;
// After the bridge stops (e.g. the Pocket is unplugged), start a new one after this delay.
const BRIDGE_RETRY_MS = 3000;
export function useVehicleTelemetry() {
  // Telemetry starts on page load; the toggle only stops (or restarts) it.
  const [enabled, setEnabled] = useState(true);
  const [retry, setRetry] = useState(0);
  const [data, setData] = useState<VehicleTelemetry | null>(null);
  const [state, setState] = useState("Connecting");
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
    // Re-render once when the latest packet goes stale, instead of polling for it.
    let expiry: ReturnType<typeof setTimeout> | undefined;
    const scheduleExpiry = () => {
      clearTimeout(expiry);
      expiry = setTimeout(() => {
        setNow(Date.now());
        resetClock();
      }, PACKET_TIMEOUT_MS + 1);
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
        scheduleExpiry();
      } catch {
        setState("Invalid telemetry");
      }
    });
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    stream.addEventListener("bridge-error", () => {
      setState("Bridge unavailable");
      resetClock();
      stream.close();
      retryTimer = setTimeout(() => setRetry((n) => n + 1), BRIDGE_RETRY_MS);
    });
    stream.onerror = () => {
      setState("Disconnected");
      resetClock();
    };
    // Flight time shows whole seconds, so a 1 s tick is enough between packets.
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => {
      stream.close();
      clearInterval(timer);
      clearTimeout(expiry);
      clearTimeout(retryTimer);
      lastPacket.current = 0;
    };
  }, [enabled, retry]);
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
  const flightTime = formatClock(seconds);
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
