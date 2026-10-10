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
  normal: {
    label: "Normal",
    pinClass: "mission-pin-neutral",
    markerClass: "",
    textClass: "text-white",
  },
  elevated: {
    label: "High temperature",
    pinClass: "mission-pin-alert",
    markerClass: "person-map-marker-alert",
    textClass: "text-[#d5ad7b] font-medium",
  },
  low: {
    label: "Low temperature",
    pinClass: "mission-pin-low",
    markerClass: "person-map-marker-low",
    textClass: "text-[#9bc9e6] font-medium",
  },
};
