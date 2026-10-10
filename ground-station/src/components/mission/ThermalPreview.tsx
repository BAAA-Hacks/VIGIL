import { ThermalImage } from "../dashboard/ThermalImage";
export function ThermalPreview() {
  return (
    <div className="mission-thermal">
      <div className="mission-thermal-heading">
        <span>Thermal camera</span>
        <span className="mission-muted">Simulated</span>
      </div>
      <ThermalImage
        frame={null}
        detection={null}
        demo
        palette="white"
        hasPerson
      />
    </div>
  );
}
