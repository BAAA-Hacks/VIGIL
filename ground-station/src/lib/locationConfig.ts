import type { LocationConfig } from "./geolocation.ts";

export function isLocationConfig(value: unknown): value is LocationConfig {
  if (!value || typeof value !== "object") return false;
  const c = value as Record<string, unknown>;
  const finite = (key: string) =>
    typeof c[key] === "number" && Number.isFinite(c[key]);
  return (
    (c.altitudeReference === "takeoff" || c.altitudeReference === "absolute") &&
    finite("startingCameraHeightM") &&
    finite("mountDownDeg") &&
    typeof c.nativeImageConfirmed === "boolean" &&
    typeof c.attitudeConventionConfirmed === "boolean" &&
    typeof c.forwardFlightConfirmed === "boolean" &&
    ["takeoffElevationM", "headingOffsetDeg", "fx", "fy", "cx", "cy"].every(
      (k) => c[k] === undefined || finite(k),
    )
  );
}
