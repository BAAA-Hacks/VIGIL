import type { Terrain } from "./geolocation.ts";

export interface TerrainGrid {
  south: number;
  west: number;
  latitudeStep: number;
  longitudeStep: number;
  /** Rows south to north, columns west to east. Null means missing coverage. */
  elevations: (number | null)[][];
}
/** Offline bilinear terrain sampler. Elevations must share the camera altitude datum. */
export function gridTerrain(grid: TerrainGrid): Terrain {
  const rows = grid.elevations.length,
    cols = grid.elevations[0]?.length ?? 0;
  if (
    rows < 2 ||
    cols < 2 ||
    grid.elevations.some((row) => row.length !== cols) ||
    ![grid.south, grid.west, grid.latitudeStep, grid.longitudeStep].every(
      Number.isFinite,
    ) ||
    grid.latitudeStep <= 0 ||
    grid.longitudeStep <= 0
  )
    throw new Error("Invalid terrain grid");
  return (lat, lon) => {
    const y = (lat - grid.south) / grid.latitudeStep,
      x = (lon - grid.west) / grid.longitudeStep;
    if (x < 0 || y < 0 || x > cols - 1 || y > rows - 1) return null;
    const r = Math.min(Math.floor(y), rows - 2),
      c = Math.min(Math.floor(x), cols - 2);
    const v = [
      grid.elevations[r][c],
      grid.elevations[r][c + 1],
      grid.elevations[r + 1][c],
      grid.elevations[r + 1][c + 1],
    ];
    if (v.some((n) => n === null || !Number.isFinite(n))) return null;
    const dx = x - c,
      dy = y - r;
    return (
      v[0]! * (1 - dx) * (1 - dy) +
      v[1]! * dx * (1 - dy) +
      v[2]! * (1 - dx) * dy +
      v[3]! * dx * dy
    );
  };
}
