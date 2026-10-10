import { useState } from "react";
import type { PinData } from "../../types/mission";
import { TEMPERATURE_STATUS } from "../../lib/temperatureStatus";
import { GroundElevation } from "./GroundElevation";
import { ThermalImage } from "./ThermalImage";

interface PersonPinProps {
  pin: PinData;
  expanded: boolean;
  onSelect: (pin: PinData) => void;
  onDelete: (pin: PinData) => void;
}

function PersonDetails({
  pin,
  onDelete,
}: {
  pin: PinData;
  onDelete: (pin: PinData) => void;
}) {
  // Freeze external lookup coordinates at selection, rather than querying every tracking update.
  const [elevationPoint] = useState(() => ({
    latitude: pin.latitude,
    longitude: pin.longitude,
  }));
  const temperature = TEMPERATURE_STATUS[pin.status];
  return (
    <div
      id={"person-details-" + pin.id}
      className="flex flex-col gap-2 bg-[var(--color-ink)]/3 px-3 pb-3"
    >
      {pin.review ? (
        <figure className="overflow-hidden rounded-[8px] border border-[color:var(--color-ink)]/15">
          <ThermalImage
            frame={pin.review.frame}
            detection={{
              frame_id: pin.review.frame.frame_id,
              processing_ms: 0,
              detections: [pin.review.detection],
            }}
            demo={false}
            palette="white"
            hasPerson
            presentation="preview"
          />
          <figcaption className="space-y-1 px-2 py-2 text-[10px] leading-relaxed text-[color:var(--color-ink)]/80">
            <p>Capture used for this location · highlighted person</p>
            <p>
              {new Date(pin.review.frame.timestamp_ms).toLocaleTimeString()} ·{" "}
              {Math.round(pin.review.detection.confidence * 100)}% detection
              confidence
            </p>
          </figcaption>
        </figure>
      ) : (
        <p className="rounded-[6px] border border-[color:var(--color-ink)]/15 p-2 text-[11px] text-[color:var(--color-ink)]/75">
          {pin.manual
            ? "Manually placed · no drone capture attached."
            : "No drone capture available for this person."}
        </p>
      )}
      <div className="flex items-center justify-between">
        <span className="text-xs text-[color:var(--color-ink)]/80">
          Coordinates
        </span>
        <span className="text-xs tabular-nums text-[color:var(--color-ink)]">
          {pin.coords}
        </span>
      </div>
      {!pin.manual && (
        <div className="flex items-center justify-between">
          <span className="text-xs text-[color:var(--color-ink)]/80">
            Temperature
          </span>
          <span className={"text-sm tabular-nums " + temperature.textClass}>
            {pin.temp}
          </span>
        </div>
      )}
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
      {pin.manual && pin.elevationState === "loading" ? (
        <p className="text-xs">Ground elevation · Looking up…</p>
      ) : pin.groundElevationM !== undefined ? (
        <p className="text-xs text-[color:var(--color-ink)]/80">
          Ground elevation used: {pin.groundElevationM.toFixed(1)} m
        </p>
      ) : (
        <GroundElevation
          latitude={elevationPoint.latitude}
          longitude={elevationPoint.longitude}
        />
      )}
      <button
        type="button"
        onClick={() => onDelete(pin)}
        className="self-start rounded-[4px] border border-[color:var(--color-ink)]/20 px-2 py-1.5 text-xs hover:bg-[var(--color-pink)]/10"
      >
        Delete person
      </button>{" "}
    </div>
  );
}

export function PersonPin({
  pin,
  expanded,
  onSelect,
  onDelete,
}: PersonPinProps) {
  const temperature = TEMPERATURE_STATUS[pin.status];
  return (
    <div className="border-b border-[color:var(--color-ink)]/12">
      <button
        type="button"
        onClick={() => onSelect(pin)}
        aria-expanded={expanded}
        aria-controls={"person-details-" + pin.id}
        className="flex w-full items-center justify-between border-0 bg-transparent px-3 py-2.5 text-left hover:bg-[var(--color-ink)]/5 focus-visible:outline-2 focus-visible:outline-[color:var(--color-ink)] focus-visible:-outline-offset-3"
      >
        <div className="flex items-center gap-2">
          <span
            className={
              "grid size-[26px] place-items-center rounded-[3px] text-[11px] tabular-nums " +
              temperature.pinClass
            }
          >
            {pin.displayLabel ?? pin.id}
          </span>
          <span className="text-xs font-medium text-[color:var(--color-ink)]">
            {pin.name}
            {!pin.manual && pin.status !== "normal" && (
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
      {expanded && <PersonDetails pin={pin} onDelete={onDelete} />}
    </div>
  );
}
