import type { PinData } from "../types/mission";

interface TemperaturePresentation {
  label: string;
  pinClass: string;
  markerClass: string;
  textClass: string;
}

// The Lepton reading is an apparent surface temperature, not a body-temperature measurement,
// so no status gets a warning label or colour: every status presents the same neutral way.
const NEUTRAL: TemperaturePresentation = {
  label: "",
  pinClass: "bg-[var(--color-ink)]/6 text-[color:var(--color-ink)]/80",
  markerClass:
    "border-[color:var(--color-ink)]/60 bg-[var(--color-paper)] text-[color:var(--color-ink)]",
  textClass: "text-[color:var(--color-ink)]",
};

export const TEMPERATURE_STATUS: Record<
  PinData["status"],
  TemperaturePresentation
> = {
  unknown: NEUTRAL,
  normal: NEUTRAL,
  elevated: NEUTRAL,
  low: NEUTRAL,
};
