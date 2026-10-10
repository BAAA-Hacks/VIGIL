import data from "./dummy-data.json";
import type { PinData, TelemetryData } from "../types/mission";

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
  latitude: person.coordinates.latitude,
  longitude: person.coordinates.longitude,
  coords: formatCoordinates(
    person.coordinates.latitude,
    person.coordinates.longitude,
  ),
  temp: `${((person.temperature_c * 9) / 5 + 32).toFixed(1)}°F`,
  status: temperatureStatus(person.temperature_status),
}));
const drone = data.drone;
const flightMinutes = Math.floor(drone.flight_time_seconds / 60);
const flightSeconds = drone.flight_time_seconds % 60;
export const MOCK_TELEMETRY: TelemetryData = {
  speed: `${drone.ground_speed_mps.toFixed(1)} m/s`,
  alt: `${drone.altitude_m.toFixed(1)} m`,
  course: `${drone.course_deg.toString().padStart(3, "0")}°`,
  dist: `${(drone.distance_from_home_m / 1000).toFixed(2)} km`,
  time: `${flightMinutes}:${flightSeconds.toString().padStart(2, "0")}`,
  coords: formatCoordinates(
    drone.coordinates.latitude,
    drone.coordinates.longitude,
  ),
  temp: `${drone.pcb_temperature_c.toFixed(1)} °C`,
};
