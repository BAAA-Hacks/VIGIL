export interface PinData {
  id: string;
  name: string;
  coords: string;
  latitude: number;
  longitude: number;
  temp: string;
  status: "normal" | "elevated" | "low";
}

export interface TelemetryData {
  speed: string;
  coords: string;

  alt: string;
  time: string;
  temp: string;
  course: string;
  dist: string;
}
