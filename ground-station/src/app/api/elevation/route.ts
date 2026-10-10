import { elevationRequestGate } from "../../../lib/elevationRateLimit";
import { NextRequest, NextResponse } from "next/server";
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
        signal: AbortSignal.timeout(12000),
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
    if (!Number.isFinite(elevation) || elevation <= -1000000) {
      return NextResponse.json(
        { error: "No USGS elevation coverage at these coordinates." },
        { status: 404 },
      );
    }
    return NextResponse.json({
      latitude,
      longitude,
      elevation_m: elevation,
      source: "USGS 3DEP / EPQS",
      resolution_m: data.resolution ?? null,
      acquisition_date: data.AcquisitionDate ?? null,
    });
  } catch {
    return NextResponse.json(
      { error: "Elevation lookup unavailable. Try again." },
      { status: 502 },
    );
  }
}
