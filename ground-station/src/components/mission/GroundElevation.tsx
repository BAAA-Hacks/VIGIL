"use client";
import { useEffect, useState } from "react";
interface GroundElevationProps {
  latitude: number;
  longitude: number;
}
export function GroundElevation({ latitude, longitude }: GroundElevationProps) {
  const [elevation, setElevation] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setElevation(null);
    setError(null);
    fetch(`/api/elevation?lat=${latitude}&lon=${longitude}`, {
      signal: controller.signal,
    })
      .then(async (response) => {
        const result = await response.json();
        if (!response.ok)
          throw new Error(result.error ?? "Elevation unavailable");
        if (
          typeof result.elevation_m !== "number" ||
          !Number.isFinite(result.elevation_m)
        )
          throw new Error("Elevation unavailable");
        if (!controller.signal.aborted) setElevation(result.elevation_m);
      })
      .catch((error) => {
        if (!controller.signal.aborted)
          setError(
            error instanceof Error ? error.message : "Elevation unavailable",
          );
      });
    return () => controller.abort();
  }, [latitude, longitude, attempt]);
  return (
    <div
      className="border-t border-[color:var(--color-ink)]/25 pt-3"
      aria-live="polite"
    >
      <div className="flex items-center justify-between">
        <span className="text-[color:var(--color-ink)]/80 text-xs">
          Ground elevation
        </span>
        <span className="text-[color:var(--color-ink)] text-xs tabular-nums">
          {elevation !== null
            ? `${elevation.toFixed(1)} m`
            : error
              ? "Unavailable"
              : "Looking up…"}
        </span>
      </div>
      <p className="leading-relaxed mt-2 text-[10px] text-[color:var(--color-ink)]/80">
        {error ??
          "USGS 3DEP · Terrain elevation, separate from drone altitude."}
      </p>
      {error && (
        <button
          className="flex items-center gap-1.5 border-0 bg-transparent p-1.5 text-[10px] text-[color:var(--color-ink)]/80"
          onClick={() => setAttempt((value) => value + 1)}
        >
          Retry lookup
        </button>
      )}
    </div>
  );
}
