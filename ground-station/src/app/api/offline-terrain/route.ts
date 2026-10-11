import { readOffline, writeOffline } from "../../../lib/offlineStore";
import { gridTerrain, type TerrainGrid } from "../../../lib/terrainGrid";
export const runtime = "nodejs";
export async function GET() {
  const bytes = await readOffline("terrain.json");
  return bytes
    ? new Response(new Uint8Array(bytes), {
        headers: {
          "Content-Type": "application/json",
          "Cache-Control": "no-store",
        },
      })
    : Response.json(null);
}
export async function POST(request: Request) {
  const text = await request.text();
  if (text.length > 8_000_000)
    return Response.json(
      { error: "Terrain file is too large" },
      { status: 413 },
    );
  try {
    const grid = JSON.parse(text) as TerrainGrid;
    if (
      !Array.isArray(grid.elevations) ||
      grid.elevations.length > 512 ||
      grid.elevations.some(
        (row) =>
          !Array.isArray(row) ||
          row.length > 512 ||
          row.some(
            (value) =>
              value !== null &&
              (typeof value !== "number" || !Number.isFinite(value)),
          ),
      )
    )
      throw new Error();
    gridTerrain(grid);
    await writeOffline("terrain.json", JSON.stringify(grid));
    return Response.json({ saved: true });
  } catch {
    return Response.json({ error: "Invalid terrain grid" }, { status: 400 });
  }
}
