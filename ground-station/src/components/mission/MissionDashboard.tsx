"use client";
import { useRef, useState } from "react";
import type { PinData } from "../../types/mission";
import { TestDataToggle } from "./TestDataToggle";
import { MissionHeader } from "./MissionHeader";
import { MapArea } from "./MapArea";
import { DroneInfoPanel } from "./DroneInfoPanel";
import { PinsPanel, type TemperatureFilter } from "./PinsPanel";
import { useVehicleTelemetry } from "../../hooks/useVehicleTelemetry";
import { usePinTest } from "../../hooks/usePinTest";
import { useThermalFeed } from "../../hooks/useThermalFeed";
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
  const thermal = useThermalFeed(!pinTest.enabled);
  const [manualPins, setManualPins] = useState<PinData[]>([]);
  const [deletedIds, setDeletedIds] = useState<Set<string>>(() => new Set());
  const [temperatureFilter, setTemperatureFilter] =
    useState<TemperatureFilter>("all");
  const manualNumber = useRef(0);
  const pins = [
    ...(locations.active ? locations.pins : MOCK_PINS),
    ...manualPins,
  ].filter((pin) => !deletedIds.has(pin.id));
  function deletePerson(pin: PinData) {
    setDeletedIds((ids) => new Set([...ids, pin.id]));
    setManualPins((items) => items.filter((item) => item.id !== pin.id));
    setExpandedId((id) => (id === pin.id ? null : id));
    setFocusedPin((item) => (item?.id === pin.id ? null : item));
  }
  async function addPerson(latitude: number, longitude: number) {
    const number = ++manualNumber.current;
    const pin: PinData = {
      id: `manual-${crypto.randomUUID()}`,
      displayLabel: `M${number}`,
      name: `Manual person ${number}`,
      manual: true,
      elevationState: "loading",
      latitude,
      longitude,
      coords: `${latitude.toFixed(6)}, ${longitude.toFixed(6)}`,
      temp: "",
      status: "unknown",
    };
    setManualPins((items) => [...items, pin]);
    setTemperatureFilter("all");
    setExpandedId(pin.id);
    try {
      const response = await fetch(
        `/api/elevation?lat=${latitude}&lon=${longitude}`,
      );
      const result = await response.json();
      if (
        !response.ok ||
        typeof result.elevation_m !== "number" ||
        !Number.isFinite(result.elevation_m)
      )
        throw new Error("Elevation unavailable");
      setManualPins((items) =>
        items.map((item) =>
          item.id === pin.id
            ? {
                ...item,
                groundElevationM: result.elevation_m,
                elevationState: undefined,
              }
            : item,
        ),
      );
    } catch {
      setManualPins((items) =>
        items.map((item) =>
          item.id === pin.id
            ? { ...item, elevationState: "unavailable" }
            : item,
        ),
      );
    }
  }
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [focusedPin, setFocusedPin] = useState<PinData | null>(null);
  const [focusRevision, setFocusRevision] = useState(0);
  function selectPerson(pin: PinData) {
    setExpandedId((current) => (current === pin.id ? null : pin.id));
    setFocusedPin(pin);
    setFocusRevision((current) => current + 1);
  }
  function selectMapPerson(pin: PinData) {
    setTemperatureFilter("all");
    setExpandedId(pin.id);
    setFocusedPin(pin);
    setFocusRevision((current) => current + 1);
  }
  return (
    <div className="bg-[var(--color-paper)] text-[color:var(--color-ink)] [font-family:Arial,Helvetica,sans-serif] min-h-screen flex flex-col">
      <MissionHeader peopleCount={pins.length} />
      <h1 className="sr-only">VIGIL search and rescue ground station</h1>
      <main
        id="mission-content"
        tabIndex={-1}
        className="grid grid-cols-1 gap-2 p-2 min-[900px]:grid-cols-12 min-[900px]:grid-rows-[minmax(400px,1fr)_auto] min-[900px]:min-h-[700px] min-[900px]:h-[calc(100vh-72px)]"
      >
        <div className="min-h-[400px] min-[900px]:col-span-9 min-[900px]:min-h-0">
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
            onAddPerson={addPerson}
          />
        </div>
        <div className="min-[900px]:col-span-3 min-[900px]:min-h-0 overflow-hidden">
          <PinsPanel
            settings={
              <LocationSettings
                telemetry={locations.telemetry ?? vehicle.data}
              />
            }
            message={pinTest.error || locations.message || thermal.message}
            reasons={locations.reasons}
            pins={pins}
            temperatureFilter={temperatureFilter}
            onTemperatureFilterChange={setTemperatureFilter}
            expandedId={expandedId}
            onSelect={selectPerson}
            onDelete={deletePerson}
          />
        </div>
        <div className="min-[900px]:col-span-12">
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
