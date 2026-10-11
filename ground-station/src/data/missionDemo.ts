import data from "./fixture";
import type { PinData } from "../types/mission";

function formatCoordinates(latitude: number, longitude: number): string {
  return `${Math.abs(latitude).toFixed(4)}° ${latitude >= 0 ? "N" : "S"}, ${Math.abs(longitude).toFixed(4)}° ${longitude >= 0 ? "E" : "W"}`;
}
function temperatureStatus(value: string): PinData["status"] {
  if (value === "normal" || value === "elevated" || value === "low")
    return value;
  throw new Error(`Invalid dummy temperature status: ${value}`);
}
export const MOCK_PINS: PinData[] = data.people.map((person) => ({
  id: person.id,
  name: person.name,
  latitude: person.coordinates.latitude - 34.053 + 28.601667,
  longitude: person.coordinates.longitude + 118.243 - 81.200556,
  coords: formatCoordinates(
    person.coordinates.latitude - 34.053 + 28.601667,
    person.coordinates.longitude + 118.243 - 81.200556,
  ),
  temp: `${((person.temperature_c * 9) / 5 + 32).toFixed(1)}°F`,
  status: temperatureStatus(person.temperature_status),
}));
