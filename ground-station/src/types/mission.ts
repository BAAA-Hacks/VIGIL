export interface PinData {
  manual?: boolean;
  elevationState?: "loading" | "unavailable";
  displayLabel?: string;
  locationNote?: string;
  capturedAt?: number;
  groundElevationM?: number;
  id: string;
  name: string;
  coords: string;
  latitude: number;
  longitude: number;
  temp: string;
  status: "normal" | "elevated" | "low" | "unknown";
}
