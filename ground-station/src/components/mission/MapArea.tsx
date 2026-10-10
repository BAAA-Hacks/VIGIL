"use client";
import { useState } from "react";
import { ArrowLeftRight } from "lucide-react";
import { ThermalImage } from "../dashboard/ThermalImage";
import { PersonMap } from "./PersonMap";
import { ViewerPane } from "./ViewerPane";
import { MapViewSelect, type MapView } from "./MapViewSelect";
import type { PinData } from "../../types/mission";

interface MapAreaProps {
  drone?: import("../../types/telemetry").VehicleTelemetry | null;
  frame?: import("../../types/vigil").ThermalFrame | null;
  detection?: import("../../types/vigil").DetectionResult | null;
  live?: boolean;
  pins: PinData[];
  focusedPin: PinData | null;
  focusRevision: number;
  onSelectPerson: (pin: PinData) => void;
}

export function MapArea(props: MapAreaProps) {
  const [thermalPrimary, setThermalPrimary] = useState(false);
  const [cornerMinimized, setCornerMinimized] = useState(false);
  const [layer, setLayer] = useState<MapView>("topographic");
  const swap = () => setThermalPrimary((value) => !value);

  return (
    <section
      className="relative isolate size-full min-h-[400px] overflow-hidden rounded-[5px] border border-[color:var(--color-ink)]/15 bg-[var(--color-paper)]"
      aria-label="Map and thermal camera"
    >
      <div className="flex h-[42px] items-center justify-between gap-3 bg-[var(--color-ink)] px-3.5 text-xs text-[color:var(--color-paper)]">
        <span>{thermalPrimary ? "Thermal camera" : "Search area"}</span>
        <MapViewSelect value={layer} onChange={setLayer} />
        <button
          type="button"
          className="flex items-center gap-1.5 border-0 bg-transparent p-1.5 text-[10px] text-[color:var(--color-paper)]/80"
          onClick={swap}
          aria-label="Swap views between map and thermal camera"
        >
          <ArrowLeftRight size={13} /> Swap views
        </button>
      </div>
      <ViewerPane
        primary={!thermalPrimary}
        kind="map"
        minimized={cornerMinimized}
        onMinimize={() => setCornerMinimized(true)}
        onRestore={() => setCornerMinimized(false)}
        onPromote={swap}
      >
        <PersonMap {...props} compact={thermalPrimary} layer={layer} />
      </ViewerPane>
      <ViewerPane
        primary={thermalPrimary}
        kind="thermal"
        minimized={cornerMinimized}
        onMinimize={() => setCornerMinimized(true)}
        onRestore={() => setCornerMinimized(false)}
        onPromote={swap}
      >
        <ThermalImage
          frame={props.frame ?? null}
          detection={props.detection ?? null}
          demo={!props.live}
          palette="white"
          presentation="viewer"
          hasPerson
        />
      </ViewerPane>
    </section>
  );
}
