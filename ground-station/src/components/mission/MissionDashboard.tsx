"use client";
import { useState } from "react";
import type { PinData } from "../../types/mission";
import { MissionHeader } from "./MissionHeader";
import { MapArea } from "./MapArea";
import { DroneInfoPanel } from "./DroneInfoPanel";
import { PinsPanel } from "./PinsPanel";
import { MOCK_PINS, MOCK_TELEMETRY } from "../../data/missionDemo";

export function MissionDashboard() {
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
    <div className="mission-station min-h-screen flex flex-col">
      <MissionHeader />
      <div className="grid grid-cols-1 gap-4 p-4 lg:p-5 lg:grid-cols-12 lg:grid-rows-[minmax(400px,1fr)_auto] lg:min-h-[700px] lg:h-[calc(100vh-72px)]">
        <div className="min-h-[400px] lg:col-span-8 lg:min-h-0">
          <MapArea
            pins={MOCK_PINS}
            focusedPin={focusedPin}
            focusRevision={focusRevision}
            onSelectPerson={selectMapPerson}
          />
        </div>
        <div className="lg:col-span-4 lg:min-h-0 overflow-hidden">
          <PinsPanel
            pins={MOCK_PINS}
            expandedId={expandedId}
            onSelect={selectPerson}
          />
        </div>
        <div className="lg:col-span-12">
          <DroneInfoPanel telemetry={MOCK_TELEMETRY} />
        </div>
      </div>
    </div>
  );
}
