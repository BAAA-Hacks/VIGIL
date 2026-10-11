import type { PinData } from "../types/mission";

interface TemperaturePresentation {
  label: string;
  pinClass: string;
  markerClass: string;
  textClass: string;
}

export const TEMPERATURE_STATUS: Record<
  PinData["status"],
  TemperaturePresentation
> = {
  unknown: {
    label: "",
    pinClass: "bg-[var(--color-ink)]/6 text-[color:var(--color-ink)]/80",
    markerClass:
      "border-[color:var(--color-ink)]/60 bg-[var(--color-paper)] text-[color:var(--color-ink)]",
    textClass: "text-[color:var(--color-ink)]",
  },
  normal: {
    label: "Normal",
    pinClass: "bg-[var(--color-ink)]/6 text-[color:var(--color-ink)]/80",
    markerClass:
      "border-[color:var(--color-ink)]/60 bg-[var(--color-paper)] text-[color:var(--color-ink)]",
    textClass: "text-[color:var(--color-ink)]",
  },
  elevated: {
    label: "High temperature",
    pinClass:
      "border border-[color:var(--color-pink)]/35 bg-[var(--color-peach)]/25 text-[color:var(--color-ink)]",
    markerClass:
      "border-[color:var(--color-pink)] bg-[color-mix(in_srgb,var(--color-peach)_80%,var(--color-paper))] text-[color:var(--color-ink)]",
    textClass: "text-[color:var(--color-ink)] font-medium",
  },
  low: {
    label: "Low temperature",
    pinClass:
      "border border-[color:var(--color-blue)]/70 bg-[var(--color-blue)]/25 text-[color:var(--color-ink)]",
    markerClass:
      "border-[color:var(--color-ink)]/60 bg-[var(--color-blue)] text-[color:var(--color-ink)]",
    textClass: "text-[color:var(--color-ink)] font-medium",
  },
};
