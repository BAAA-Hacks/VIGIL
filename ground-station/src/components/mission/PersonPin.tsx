import { useState } from "react";
import type { PinData } from "../../types/mission";
import { TEMPERATURE_STATUS } from "../../lib/temperatureStatus";
import { GroundElevation } from "./GroundElevation";

interface PersonPinProps {
  pin: PinData;
  expanded: boolean;
  onSelect: (pin: PinData) => void;
}

function PersonDetails({ pin }: { pin: PinData }) {
  // Freeze external lookup coordinates at selection, rather than querying every tracking update.
  const [elevationPoint] = useState(() => ({
    latitude: pin.latitude,
    longitude: pin.longitude,
  }));
  const temperature = TEMPERATURE_STATUS[pin.status];
  return (
    <div
      id={"person-details-" + pin.id}
      className="flex flex-col gap-3 bg-[var(--color-ink)]/3 px-[18px] pb-[18px]"
    >
      <div className="flex items-center justify-between">
        <span className="text-xs text-[color:var(--color-ink)]/80">
          Coordinates
        </span>
        <span className="text-xs tabular-nums text-[color:var(--color-ink)]">
          {pin.coords}
        </span>
      </div>
      <div className="flex items-center justify-between">
        <span className="text-xs text-[color:var(--color-ink)]/80">
          Temperature
        </span>
        <span className={"text-sm tabular-nums " + temperature.textClass}>
          {pin.temp}
        </span>
      </div>
      {pin.locationNote && (
        <p className="text-xs text-[color:var(--color-ink)]/80">
          {pin.locationNote}
          {pin.capturedAt &&
            ` · ${new Date(pin.capturedAt).toLocaleTimeString()}`}
        </p>
      )}
      {pin.locationNote && pin.groundElevationM === undefined && (
        <p className="text-xs text-[color:var(--color-ink)]/80">
          Ground elevation lookup uses the position at selection.
        </p>
      )}
      {pin.groundElevationM !== undefined ? (
        <p className="text-xs text-[color:var(--color-ink)]/80">
          Ground elevation used: {pin.groundElevationM.toFixed(1)} m
        </p>
      ) : (
        <GroundElevation
          latitude={elevationPoint.latitude}
          longitude={elevationPoint.longitude}
        />
      )}
    </div>
  );
}

export function PersonPin({ pin, expanded, onSelect }: PersonPinProps) {
  const temperature = TEMPERATURE_STATUS[pin.status];
  return (
    <div className="border-b border-[color:var(--color-ink)]/12">
      <button
        type="button"
        onClick={() => onSelect(pin)}
        aria-expanded={expanded}
        aria-controls={"person-details-" + pin.id}
        className="flex w-full items-center justify-between border-0 bg-transparent px-[18px] py-[17px] text-left hover:bg-[var(--color-ink)]/5 focus-visible:outline-2 focus-visible:outline-[color:var(--color-ink)] focus-visible:-outline-offset-3"
      >
        <div className="flex items-center gap-3">
          <span
            className={
              "grid size-[26px] place-items-center rounded-[3px] text-[11px] tabular-nums " +
              temperature.pinClass
            }
          >
            {pin.displayLabel ?? pin.id}
          </span>
          <span className="text-sm font-medium text-[color:var(--color-ink)]">
            {pin.name}
            {pin.status !== "normal" && (
              <span
                className={"mt-1 block text-[10px] " + temperature.textClass}
              >
                {temperature.label}
              </span>
            )}
          </span>
        </div>
        <span className="text-lg leading-none text-[color:var(--color-ink)]/80">
          {expanded ? "-" : "+"}
        </span>
      </button>
      {expanded && <PersonDetails pin={pin} />}
    </div>
  );
}
