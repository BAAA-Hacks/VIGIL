import type { PinData, TelemetryData } from "../types/mission";
export const MOCK_PINS: PinData[] = [
  {
    id: "1",
    latitude: 34.0522,
    longitude: -118.2437,
    name: "Person 1",
    coords: "34.0522° N, 118.2437° W",
    temp: "98.6°F",
    status: "normal",
  },
  {
    id: "2",
    latitude: 34.053,
    longitude: -118.242,
    name: "Person 2",
    coords: "34.0530° N, 118.2420° W",
    temp: "101.2°F",
    status: "elevated",
  },
  {
    id: "3",
    latitude: 34.0515,
    longitude: -118.245,
    name: "Person 3",
    coords: "34.0515° N, 118.2450° W",
    temp: "94.0°F",
    status: "low",
  },
  {
    id: "4",
    latitude: 34.0541,
    longitude: -118.2411,
    name: "Person 4",
    coords: "34.0541° N, 118.2411° W",
    temp: "98.2°F",
    status: "normal",
  },
  {
    id: "5",
    latitude: 34.0555,
    longitude: -118.2405,
    name: "Person 5",
    coords: "34.0555° N, 118.2405° W",
    temp: "99.1°F",
    status: "normal",
  },
];

export const MOCK_TELEMETRY: TelemetryData = {
  speed: "15.4 m/s",
  coords: "34.0525° N, 118.2430° W",
  alt: "120.5 m",
  time: "24:15",
  temp: "42.3 °C",
  course: "045° NE",
  dist: "1.24 km",
};
