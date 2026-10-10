import { offsetCoordinates } from "./geolocation.ts";

export const SHAPE_POINTS = {
  circle: 10,
  square: 4,
  triangle: 3,
  line: 2,
} as const;
export type PathShapeKind = keyof typeof SHAPE_POINTS;
export interface PathShape {
  id: string;
  kind: PathShapeKind;
  latitude: number;
  longitude: number;
  sizeM: number;
}
export interface MissionWaypoint {
  latitude: number;
  longitude: number;
  altitudeM: number;
  speedMs: number;
}
export interface PathMission {
  waypoints: MissionWaypoint[];
  altitudeReference: "home" | "amsl";
  finish: "hold";
}

export function shapeCoordinates(shape: PathShape) {
  const r = shape.sizeM;
  const offsets: [number, number][] =
    shape.kind === "square"
      ? [
          [r, -r],
          [r, r],
          [-r, r],
          [-r, -r],
        ]
      : shape.kind === "line"
        ? [
            [0, -r],
            [0, r],
          ]
        : Array.from({ length: SHAPE_POINTS[shape.kind] }, (_, i) => {
            const angle = (i * 2 * Math.PI) / SHAPE_POINTS[shape.kind];
            return [r * Math.cos(angle), r * Math.sin(angle)] as [
              number,
              number,
            ];
          });
  return offsets.map(([north, east]) =>
    offsetCoordinates(shape.latitude, shape.longitude, north, east),
  );
}

export function createPathMission(
  shapes: PathShape[],
  altitudeM: number,
  speedMs: number,
  altitudeReference: PathMission["altitudeReference"],
): PathMission {
  const mission: PathMission = {
    waypoints: shapes.flatMap((shape) =>
      shapeCoordinates(shape).map((point) => ({
        ...point,
        altitudeM,
        speedMs,
      })),
    ),
    altitudeReference,
    finish: "hold",
  };
  if (!isPathMission(mission))
    throw new Error(
      "Enter a valid altitude, speed, and route of 2–60 waypoints",
    );
  return mission;
}

export function isPathMission(value: unknown): value is PathMission {
  if (!value || typeof value !== "object") return false;
  const m = value as PathMission;
  return (
    m.finish === "hold" &&
    ["home", "amsl"].includes(m.altitudeReference) &&
    Array.isArray(m.waypoints) &&
    m.waypoints.length >= 2 &&
    m.waypoints.length <= 60 &&
    m.waypoints.every(
      (p) =>
        p &&
        [p.latitude, p.longitude, p.altitudeM, p.speedMs].every(
          Number.isFinite,
        ) &&
        Math.abs(p.latitude) < 85 &&
        Math.abs(p.longitude) <= 180 &&
        p.altitudeM >= (m.altitudeReference === "home" ? 1 : -500) &&
        p.altitudeM <= 10000 &&
        p.speedMs >= 0.1 &&
        p.speedMs <= 20,
    )
  );
}

/** Leave the final action as WAYPOINT: INAV holds indefinitely on completion. */
export function missionXml(mission: PathMission) {
  if (!isPathMission(mission)) throw new Error("Invalid mission");
  const items = mission.waypoints.map(
    (p, i) =>
      `  <missionitem no="${i + 1}" action="WAYPOINT" lat="${p.latitude.toFixed(7)}" lon="${p.longitude.toFixed(7)}" alt="${Math.round(p.altitudeM)}" parameter1="${Math.round(p.speedMs * 100)}" parameter2="0" parameter3="${mission.altitudeReference === "amsl" ? 1 : 0}" />`,
  );
  return `<?xml version="1.0" encoding="utf-8"?>\n<mission>\n${items.join("\n")}\n</mission>\n`;
}
