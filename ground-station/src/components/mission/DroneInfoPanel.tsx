import type { TelemetryData } from "../../types/mission";
import { StatBox } from "./StatBox";
export function DroneInfoPanel({ telemetry }: { telemetry: TelemetryData }) {
  return (
    <div className="mission-panel h-full flex flex-col">
      <div className="mission-panel-heading">
        <h2 className="mission-panel-title">Drone Info</h2>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-7 gap-x-5 gap-y-4 p-5 flex-grow">
        <StatBox label="Ground Speed" value={telemetry.speed} />
        <StatBox label="Altitude" value={telemetry.alt} />
        <StatBox label="Course" value={telemetry.course} />
        <StatBox label="Distance from home" value={telemetry.dist} />

        <StatBox label="Flight Time" value={telemetry.time} />
        <StatBox label="Coordinates" value={telemetry.coords} />
        <StatBox
          label="Board temperature"
          value={telemetry.temp}
          highlight={true}
        />
      </div>
    </div>
  );
}
