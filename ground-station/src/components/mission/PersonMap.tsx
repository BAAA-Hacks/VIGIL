"use client";
import { useEffect, useRef, useState } from "react";
import { PersonMapController } from "../../lib/personMapController";
import type { VehicleTelemetry } from "../../types/telemetry";
import type { MapView } from "./MapViewSelect";
import type { PinData } from "../../types/mission";

interface PersonMapProps {
  drone?: VehicleTelemetry | null;
  pins: PinData[];
  focusedPin: PinData | null;
  focusRevision: number;
  onSelectPerson: (pin: PinData) => void;
  compact: boolean;
  layer: MapView;
}

export function PersonMap(props: PersonMapProps) {
  const container = useRef<HTMLDivElement>(null);
  const controller = useRef<PersonMapController | null>(null);
  const latest = useRef(props);
  const [error, setError] = useState(false);

  useEffect(() => {
    latest.current = props;
    const map = controller.current;
    if (!map) return;
    map.update(props.pins, props.drone);
    // Markers are updated synchronously before opening the selected popup.
    map.focus(props.focusedPin, props.focusRevision);
    map.setLayer(props.layer);
  }, [props]);

  useEffect(() => {
    let disposed = false;
    const host = container.current;
    if (!host) return;
    import("leaflet")
      .then((L) => {
        if (disposed) return;
        const current = latest.current;
        const map = new PersonMapController(
          L,
          host,
          current.layer,
          (pin) => latest.current.onSelectPerson(pin),
          current.pins,
          current.drone,
        );
        controller.current = map;
        map.focus(current.focusedPin, current.focusRevision);
      })
      .catch(() => {
        if (!disposed) setError(true);
      });
    return () => {
      disposed = true;
      controller.current?.dispose();
      controller.current = null;
    };
  }, []);

  useEffect(() => {
    controller.current?.resize();
  }, [props.compact]);

  return (
    <div className="relative size-full [&_.leaflet-control-attribution]:max-w-[80%] [&_.leaflet-control-attribution]:text-[9px] [&_.leaflet-control-attribution_a]:text-[color:var(--color-ink)]">
      <div
        ref={container}
        className="size-full bg-[var(--color-paper)]"
        aria-label="Map of detected person coordinates"
      />
      {error && (
        <p
          role="status"
          className="absolute inset-x-2.5 top-1/2 z-[1000] bg-[var(--color-paper)] p-3 text-xs leading-relaxed text-[color:var(--color-ink)]/70"
        >
          Map could not load. Person coordinates remain available in the list.
        </p>
      )}
    </div>
  );
}
