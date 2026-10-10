import { readOffline, writeOffline } from "../../../lib/offlineStore";
import { gridTerrain, type TerrainGrid } from "../../../lib/terrainGrid";
import { elevationRequestGate } from "../../../lib/elevationRateLimit";
import {
  cachedElevation,
  elevationKey,
  storeElevation,
  type ElevationAnswer,
} from "../../../lib/elevationCache";
import { NextRequest, NextResponse } from "next/server";
const respond = ({ status, body }: ElevationAnswer) =>
  NextResponse.json(body, {
    status,
    headers: { "Cache-Control": "private, max-age=86400" },
  });
export async function GET(request: NextRequest) {
  const lat = request.nextUrl.searchParams.get("lat");
  const lon = request.nextUrl.searchParams.get("lon");
  const latitude = Number(lat),
    longitude = Number(lon);
  if (
    !lat ||
    !lon ||
    !Number.isFinite(latitude) ||
    !Number.isFinite(longitude) ||
    Math.abs(latitude) > 90 ||
    Math.abs(longitude) > 180
  ) {
    return NextResponse.json(
      { error: "Valid latitude and longitude are required." },
      { status: 400 },
    );
  }
  const key = elevationKey(latitude, longitude);
  const terrainBytes = await readOffline("terrain.json");
  if (terrainBytes) {
    try {
      const elevation = gridTerrain(
        JSON.parse(terrainBytes.toString()) as TerrainGrid,
      )(latitude, longitude);
      if (elevation !== null)
        return respond({
          status: 200,
          body: {
            latitude,
            longitude,
            elevation_m: elevation,
            source: "Imported offline terrain grid",
          },
        });
    } catch {
      /* Fall through to saved point readings. */
    }
  }
  const saved = await readOffline(`elevation/${key}.json`);
  if (saved) {
    try {
      const answer = JSON.parse(saved.toString()) as ElevationAnswer;
      if (
        answer.status === 200 &&
        typeof answer.body.elevation_m === "number" &&
        Number.isFinite(answer.body.elevation_m)
      )
        return respond(answer);
    } catch {
      /* Retry corrupted entries online. */
    }
  }
  const cached = cachedElevation(key);
  if (cached) return respond(cached);
  const url = new URL("https://epqs.nationalmap.gov/v1/json");
  url.search = new URLSearchParams({
    x: String(longitude),
    y: String(latitude),
    wkid: "4326",
    units: "Meters",
    includeDate: "true",
  }).toString();
  try {
    const response = await elevationRequestGate(() => {
      if (request.signal.aborted) throw new Error("Request cancelled");
      return fetch(url, {
        signal: AbortSignal.timeout(5000),
        next: { revalidate: 86400 },
      });
    });
    if (!response.ok) throw new Error("Service unavailable");
    const data = await response.json();
    const elevation =
      typeof data.value === "number"
        ? data.value
        : typeof data.value === "string" && data.value.trim()
          ? Number(data.value)
          : NaN;
    const answer: ElevationAnswer =
      !Number.isFinite(elevation) || elevation <= -1000000
        ? {
            status: 404,
            body: { error: "No USGS elevation coverage at these coordinates." },
          }
        : {
            status: 200,
            body: {
              latitude,
              longitude,
              elevation_m: elevation,
              source: "USGS 3DEP / EPQS",
              resolution_m: data.resolution ?? null,
              acquisition_date: data.AcquisitionDate ?? null,
            },
          };
    storeElevation(key, answer);
    if (answer.status === 200)
      await writeOffline(`elevation/${key}.json`, JSON.stringify(answer));
    return respond(answer);
  } catch {
    return NextResponse.json(
      {
        error:
          "No saved elevation here. Connect to internet or import terrain for this area.",
      },
      { status: 502 },
    );
  }
}
