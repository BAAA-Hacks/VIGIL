"use client";
import { useEffect, useState } from "react";
import {
  createPinTestSample,
  pinTestPixels,
  PIN_TEST_CONFIG,
} from "../lib/pinTest";

export function usePinTest() {
  const [enabled, setEnabled] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!enabled) return;
    const canvas = document.createElement("canvas");
    canvas.width = 160;
    canvas.height = 120;
    const context = canvas.getContext("2d");
    if (!context) {
      setError("Pin test could not render the thermal image");
      setEnabled(false);
      return;
    }
    context.putImageData(new ImageData(pinTestPixels(), 160, 120), 0, 0);
    const payload = canvas.toDataURL("image/png");
    const started = Date.now();
    const tick = () => {
      try {
        const sample = createPinTestSample(Date.now(), payload);
        window.dispatchEvent(
          new CustomEvent("vigil:telemetry", { detail: sample.telemetry }),
        );
        window.dispatchEvent(
          new CustomEvent("vigil:frame", { detail: sample.frame }),
        );
        window.dispatchEvent(
          new CustomEvent("vigil:detection", { detail: sample.detection }),
        );
        setSeconds(Math.floor((Date.now() - started) / 1000));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Invalid pin-test data");
        setEnabled(false);
      }
    };
    // Wait until the location adapter has installed its test configuration/listeners.
    const first = setTimeout(tick, 0);
    const timer = setInterval(tick, 200);
    return () => {
      clearTimeout(first);
      clearInterval(timer);
    };
  }, [enabled]);
  return {
    enabled,
    config: enabled ? PIN_TEST_CONFIG : null,
    error,
    flightTime: `${Math.floor(seconds / 60)
      .toString()
      .padStart(2, "0")}:${(seconds % 60).toString().padStart(2, "0")}`,
    toggle: () => {
      setError("");
      setSeconds(0);
      setEnabled((v) => !v);
    },
    stop: () => {
      setEnabled(false);
      setSeconds(0);
    },
  };
}
