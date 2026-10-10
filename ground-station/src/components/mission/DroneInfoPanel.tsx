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

export function DroneInfoPanel({
  telemetry,
  state,
  stale,
  flightTime,
}: DroneInfoProps) {
  const data = stale || state !== "Connected" ? null : telemetry;
  const readings = getDroneReadings(data, flightTime);

  return (
    <MissionPanel
      title="Drone Info"
      meta={
        <>
          {telemetry?.source ?? "Bridge"} · {state} ·{" "}
          {telemetry?.link_state ?? "No data"}
        </>
      }
    >
      <div className="grid grid-cols-2 gap-x-5 gap-y-4 p-5 md:grid-cols-4 xl:grid-cols-7">
        {readings.map((reading) => (
          <StatBox key={reading.label} {...reading} />
        ))}
      </div>
    </MissionPanel>
  );
}
