"use client";
import { ChevronDown } from "lucide-react";
import type { VehicleTelemetry } from "../../types/telemetry";
import { getDroneReadings } from "../../lib/droneReadings";
import { MissionPanel } from "./MissionPanel";
import { StatBox } from "./StatBox";

interface DroneInfoProps {
  telemetry: VehicleTelemetry | null;
  state: string;
  stale: boolean;
  flightTime: string;
}

const summaryLabels = [
  "Arming / mode",
  "Flight time",
  "Altitude (above home)",
  "Ground speed",
];

export function DroneInfoPanel({
  telemetry,
  state,
  stale,
  flightTime,
}: DroneInfoProps) {
  const data = stale || state !== "Connected" ? null : telemetry;
  const readings = getDroneReadings(data, flightTime);
  const byLabel = new Map(readings.map((reading) => [reading.label, reading]));
  const groups = [
    {
      title: "Navigation",
      labels: [
        "Coordinates",
        "Altitude (sea level)",
        "Course",
        "Satellites / GPS fix",
      ],
    },
    {
      title: "Attitude",
      labels: [
        data?.yaw_reference === "relative" ? "Relative yaw" : "Yaw",
        "Roll / pitch",
        "Climb rate",
      ],
    },
    {
      title: "Radio",
      labels: ["Uplink quality / RSSI", "Downlink quality / RSSI"],
    },
    {
      title: "Sensors",
      labels: ["Accelerometer (x / y / z)", "Gyro (x / y / z)", "Compass"],
    },
  ];

  function reading(label: string) {
    const item = byLabel.get(label);
    return item ? <StatBox key={label} {...item} /> : null;
  }

  return (
    <MissionPanel
      title="Drone Info"
      meta={
        <span className="flex items-center gap-1.5">
          {telemetry?.source === "replay-track" && (
            <span className="rounded-[3px] bg-[var(--color-yellow)] px-1.5 py-0.5 text-[10px] font-bold text-[color:var(--color-ink)]">
              Reconstructed flight
            </span>
          )}
          {stale ? "Telemetry stale" : state}
        </span>
      }
    >
      <div className="grid grid-cols-2 gap-x-5 gap-y-3 px-[18px] py-3 md:grid-cols-4">
        {summaryLabels.map(reading)}
      </div>
      <details
        className="group scroll-mt-4 border-t border-[color:var(--color-ink)]/15"
        onToggle={(event) => {
          const details = event.currentTarget;
          if (!details.open) return;
          details.scrollIntoView({
            behavior: window.matchMedia("(prefers-reduced-motion: reduce)")
              .matches
              ? "instant"
              : "smooth",
            block: "start",
          });
        }}
      >
        <summary className="flex cursor-pointer list-none items-center gap-2 px-[18px] py-2.5 text-xs font-medium focus-visible:outline-2 focus-visible:outline-offset-[-3px] focus-visible:outline-[color:var(--color-ink)] [&::-webkit-details-marker]:hidden">
          <ChevronDown
            aria-hidden="true"
            size={14}
            className="shrink-0 transition-transform group-open:rotate-180"
          />
          More drone details
          <span className="ml-auto hidden text-[10px] font-normal text-[color:var(--color-ink)]/80 sm:inline">
            Navigation · Attitude · Radio · Sensors
          </span>
        </summary>
        <div className="grid max-h-60 grid-cols-1 gap-5 overflow-y-auto border-t border-[color:var(--color-ink)]/10 px-[18px] py-3 md:grid-cols-2 xl:grid-cols-4">
          {groups.map((group) => (
            <section key={group.title} aria-label={group.title}>
              <h3 className="mb-3 text-xs font-semibold">{group.title}</h3>
              <div className="grid gap-3">{group.labels.map(reading)}</div>
            </section>
          ))}
          <p className="border-t border-[color:var(--color-ink)]/10 pt-2 text-[10px] text-[color:var(--color-ink)]/80 md:col-span-2 xl:col-span-4">
            Source: {telemetry?.source ?? "Bridge"} · Radio link:{" "}
            {telemetry?.link_state ?? "No data"}
          </p>
        </div>
      </details>
    </MissionPanel>
  );
}
