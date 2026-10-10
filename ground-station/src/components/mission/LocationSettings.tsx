"use client";
import { useEffect, useRef, useState } from "react";
import type { VehicleTelemetry } from "../../types/telemetry";
import { validFix } from "../../lib/geolocation";
import { dispatchVigil } from "../../lib/events";

export function LocationSettings({
  telemetry,
}: {
  telemetry: VehicleTelemetry | null;
}) {
  const [ground, setGround] = useState("");
  const [mount, setMount] = useState("20");
  const [offset, setOffset] = useState("");
  const [clock, setClock] = useState("0");
  const [confirmed, setConfirmed] = useState(false);
  const [forward, setForward] = useState(false);
  const [message, setMessage] = useState(
    "Waiting for GPS to read reference ground elevation",
  );
  const reference = useRef<{ lat: number; lon: number } | null>(null);
  const [retry, setRetry] = useState(0);
  const lookup = useRef<AbortController | null>(null);
  // Only unmount cancels the lookup; telemetry updates must not (see below).
  useEffect(() => () => lookup.current?.abort(), []);
  useEffect(() => {
    if (
      !telemetry ||
      telemetry.source === "synthetic-pin-test" ||
      !validFix(telemetry) ||
      reference.current
    )
      return;
    const lat = telemetry.lat!,
      lon = telemetry.lon!;
    reference.current = { lat, lon };
    lookup.current?.abort();
    const controller = new AbortController();
    lookup.current = controller;
    setMessage("Reading reference ground elevation…");
    fetch(`/api/elevation?lat=${lat}&lon=${lon}`, { signal: controller.signal })
      .then(async (response) => {
        const value = await response.json().catch(() => ({}));
        if (!response.ok)
          throw new Error(value.error ?? "Elevation lookup failed");
        if (!Number.isFinite(value.elevation_m))
          throw new Error("No terrain coverage");
        setGround(String(value.elevation_m));
        setMessage(
          `Reference ground at ${lat.toFixed(5)}, ${lon.toFixed(5)} · USGS`,
        );
      })
      .catch((error) => {
        if (!controller.signal.aborted)
          setMessage(
            error instanceof Error ? error.message : "Elevation unavailable",
          );
      });
    // The first valid position is fixed for this session, rather than queried every packet.
    // Do not abort on subsequent telemetry updates: that would discard the one-shot lookup.
  }, [telemetry, retry]);
  function apply() {
    if (
      !confirmed ||
      !ground ||
      ![Number(ground), Number(mount), Number(clock)].every(Number.isFinite) ||
      (offset !== "" && !Number.isFinite(Number(offset)))
    ) {
      setMessage("Enter valid values and confirm the conventions");
      return;
    }
    dispatchVigil("locationConfig", {
      altitudeReference: "absolute",
      takeoffElevationM: Number(ground),
      startingCameraHeightM: 0,
      mountDownDeg: Number(mount),
      frameClockOffsetMs: Number(clock),
      nativeImageConfirmed: true,
      attitudeConventionConfirmed: true,
      forwardFlightConfirmed: forward,
      ...(offset !== "" ? { headingOffsetDeg: Number(offset) } : {}),
    });
    setMessage("Settings applied · waiting for matched live inputs");
  }
  const input =
    "w-full rounded border border-[color:var(--color-ink)]/25 bg-[var(--color-paper)] px-2 py-1 text-xs";
  return (
    <details className="border-b border-[color:var(--color-ink)]/15 p-3 text-xs">
      <summary className="cursor-pointer font-medium">
        Location settings
      </summary>
      <div className="mt-3 grid grid-cols-2 gap-2">
        <label>
          Reference ground (m)
          <input
            className={input}
            type="number"
            step="any"
            value={ground}
            onChange={(e) => setGround(e.target.value)}
          />
        </label>
        <label>
          Camera down angle (°)
          <input
            className={input}
            type="number"
            min="0"
            max="90"
            value={mount}
            onChange={(e) => setMount(e.target.value)}
          />
        </label>
        <label>
          Yaw → north offset (°)
          <input
            className={input}
            type="number"
            placeholder="Auto from forward GPS course"
            value={offset}
            onChange={(e) => setOffset(e.target.value)}
          />
        </label>
        <label>
          Frame clock offset (ms)
          <input
            className={input}
            type="number"
            value={clock}
            onChange={(e) => setClock(e.target.value)}
          />
        </label>
      </div>
      <p className="mt-2 leading-relaxed">
        Altitude is above sea level. Reference ground is held constant for the
        flat-ground estimate. Verify the altitude and ground elevation use
        compatible vertical datums.
      </p>
      <label className="mt-2 flex items-start gap-2">
        <input
          type="checkbox"
          checked={confirmed}
          onChange={(e) => setConfirmed(e.target.checked)}
        />
        Native 160 × 120 image, synchronized clocks, pitch nose-up and roll
        right-wing-down confirmed.
      </label>
      <label className="mt-2 flex items-start gap-2">
        <input
          type="checkbox"
          checked={forward}
          onChange={(e) => setForward(e.target.checked)}
        />
        Steady forward flight for GPS heading calibration.
      </label>
      <div className="mt-3 flex gap-3">
        <button
          type="button"
          onClick={apply}
          className="rounded bg-[var(--color-ink)] px-3 py-1.5 text-[color:var(--color-paper)]"
        >
          Apply
        </button>
        <button
          type="button"
          onClick={() => {
            reference.current = null;
            setRetry((n) => n + 1);
          }}
          className="underline"
        >
          Refresh reference ground
        </button>
      </div>
      <p className="mt-2 text-[color:var(--color-ink)]/80" role="status">
        {message}
      </p>
    </details>
  );
}
