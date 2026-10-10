"use client";
import { useEffect, useState } from "react";
import { dispatchVigil } from "../lib/events";
import { ThermalPairs } from "../lib/thermalTransport";

/** Socket.IO is loaded separately from the initial dashboard bundle. */
export function useThermalFeed(enabled: boolean) {
  const [message, setMessage] = useState("Waiting for thermal feed");
  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    let disconnect: (() => void) | undefined;
    const pairs = new ThermalPairs();
    void import("socket.io-client")
      .then(({ io }) => {
        if (cancelled) return;
        const url =
          process.env.NEXT_PUBLIC_THERMAL_SOCKET_URL || "http://127.0.0.1:5000";
        const namespace =
          process.env.NEXT_PUBLIC_THERMAL_SOCKET_NAMESPACE || "/";
        const socket = io(`${url.replace(/\/$/, "")}${namespace}`, {
          autoConnect: false,
        });
        disconnect = () => {
          socket.removeAllListeners();
          socket.disconnect();
          pairs.reset();
        };
        socket.on("connect", () => {
          pairs.reset();
          setMessage("Waiting for camera frames");
        });
        socket.on("disconnect", () => {
          pairs.reset();
          setMessage("Thermal feed disconnected");
        });
        socket.on("connect_error", () =>
          setMessage("Thermal feed disconnected"),
        );
        const receive = (kind: "frame" | "detection", raw: unknown) => {
          const pair = pairs.push(kind, raw);
          if (!pair) return;
          dispatchVigil("frame", pair.frame);
          dispatchVigil("detection", pair.detection);
          setMessage("");
        };
        socket.on(
          process.env.NEXT_PUBLIC_THERMAL_FRAME_EVENT || "vigil:frame",
          (raw: unknown) => receive("frame", raw),
        );
        socket.on(
          process.env.NEXT_PUBLIC_THERMAL_DETECTION_EVENT || "vigil:detection",
          (raw: unknown) => receive("detection", raw),
        );
        socket.connect();
      })
      .catch(() => {
        if (!cancelled) setMessage("Thermal feed unavailable");
      });
    return () => {
      cancelled = true;
      disconnect?.();
    };
  }, [enabled]);
  return { message: enabled ? message : "" };
}
