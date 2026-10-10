"use client";
import { TEMPERATURE_STATUS } from "../../lib/temperatureStatus";

import type { PinData } from "../../types/mission";
interface PinsPanelProps {
  pins: PinData[];
  expandedId: string | null;
  onSelect: (pin: PinData) => void;
}
export function PinsPanel({ pins, expandedId, onSelect }: PinsPanelProps) {
  return (
    <div className="mission-panel h-full flex flex-col">
      <div className="mission-panel-heading">
        <h2 className="mission-panel-title">Marked locations</h2>
      </div>

      <div className="flex-col flex overflow-y-auto custom-scrollbar">
        {pins.map((pin) => (
          <div key={pin.id} className="mission-pin">
            <button
              onClick={() => onSelect(pin)}
              aria-expanded={expandedId === pin.id}
              aria-controls={`person-details-${pin.id}`}
              className="mission-pin-button"
            >
              <div className="flex items-center gap-3">
                <div
                  className={`mission-pin-id ${TEMPERATURE_STATUS[pin.status].pinClass}`}
                >
                  {pin.id}
                </div>
                <span className="text-[#e4e4e7] text-sm font-medium">
                  {pin.name}
                  {pin.status !== "normal" && (
                    <span
                      className={`block text-[10px] mt-1 ${TEMPERATURE_STATUS[pin.status].textClass}`}
                    >
                      {TEMPERATURE_STATUS[pin.status].label}
                    </span>
                  )}
                </span>
              </div>
              <span className="text-[#8c939a] text-lg leading-none">
                {expandedId === pin.id ? "-" : "+"}
              </span>
            </button>

            {expandedId === pin.id && (
              <div
                className="mission-pin-details"
                id={`person-details-${pin.id}`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-[#8c939a] text-xs">Coordinates</span>
                  <span className="text-[#c9cdd1] text-xs tabular-nums">
                    {pin.coords}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[#8c939a] text-xs">Temperature</span>
                  <span
                    className={`text-sm tabular-nums ${TEMPERATURE_STATUS[pin.status].textClass}`}
                  >
                    {pin.temp}
                  </span>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
