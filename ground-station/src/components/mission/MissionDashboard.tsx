"use client";
import { useState } from "react";
import type { PinData } from "../../types/mission";
import { TestDataToggle } from "./TestDataToggle";
import { MissionHeader } from "./MissionHeader";
import { MapArea } from "./MapArea";
import { DroneInfoPanel } from "./DroneInfoPanel";
import { PinsPanel } from "./PinsPanel";
import { useVehicleTelemetry } from "../../hooks/useVehicleTelemetry";
import { usePinTest } from "../../hooks/usePinTest";
import { usePersonLocations } from "../../hooks/usePersonLocations";
import { LocationSettings } from "./LocationSettings";
import { MOCK_PINS } from "../../data/missionDemo";

export function MissionDashboard() {
  const vehicle = useVehicleTelemetry();
  const pinTest = usePinTest();
  const locations = usePersonLocations(
    pinTest.enabled ? null : vehicle.data,
    pinTest.config,
  );
  const pins = locations.active ? locations.pins : MOCK_PINS;
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [focusedPin, setFocusedPin] = useState<PinData | null>(null);
  const [focusRevision, setFocusRevision] = useState(0);
  function selectPerson(pin: PinData) {
    setExpandedId((current) => (current === pin.id ? null : pin.id));
    setFocusedPin(pin);
    setFocusRevision((current) => current + 1);
  }
  function selectMapPerson(pin: PinData) {
    setExpandedId(pin.id);
    setFocusedPin(pin);
    setFocusRevision((current) => current + 1);
  }
  return (
    <div className="bg-[var(--color-paper)] text-[color:var(--color-ink)] min-h-screen flex flex-col">
      <MissionHeader />
      <h1 className="sr-only">VIGIL search and rescue ground station</h1>
      <main
        id="mission-content"
        tabIndex={-1}
        className="grid grid-cols-1 gap-4 p-4 lg:p-5 lg:grid-cols-12 lg:grid-rows-[minmax(400px,1fr)_auto] lg:min-h-[700px] lg:h-[calc(100vh-72px)]"
      >
        <div className="min-h-[400px] lg:col-span-8 lg:min-h-0">
          <MapArea
            pins={pins}
            drone={locations.drone}
            frame={locations.frame}
            detection={locations.detection}
            live={locations.active}
            focusedPin={
              (focusedPin && pins.find((p) => p.id === focusedPin.id)) || null
            }
            focusRevision={focusRevision}
            onSelectPerson={selectMapPerson}
          />
        </div>
        <div className="lg:col-span-4 lg:min-h-0 overflow-hidden">
          <PinsPanel
            settings={
              <LocationSettings
                telemetry={locations.telemetry ?? vehicle.data}
              />
            }
            message={pinTest.error || locations.message}
            reasons={locations.reasons}
            pins={pins}
            expandedId={expandedId}
            onSelect={selectPerson}
          />
        </div>
        <div className="lg:col-span-12">
          <DroneInfoPanel
            telemetry={locations.telemetry ?? vehicle.data}
            state={pinTest.enabled ? "Connected" : vehicle.state}
            stale={pinTest.enabled ? false : vehicle.stale}
            flightTime={
              pinTest.enabled ? pinTest.flightTime : vehicle.flightTime
            }
          />
        </div>
      </main>
      <TestDataToggle
        enabled={vehicle.enabled}
        onToggle={() => {
          pinTest.stop();
          vehicle.toggleTestData();
        }}
        pinTestEnabled={pinTest.enabled}
        onTogglePinTest={() => {
          if (vehicle.enabled) vehicle.toggleTestData();
          pinTest.toggle();
        }}
      />
    </div>
  );
}
