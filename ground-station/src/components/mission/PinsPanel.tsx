"use client";
import type { ReactNode } from "react";
import type { PinData } from "../../types/mission";
import { MissionPanel } from "./MissionPanel";
import { PersonPin } from "./PersonPin";

interface PinsPanelProps {
  settings?: ReactNode;
  message?: string;
  reasons?: string[];
  pins: PinData[];
  expandedId: string | null;
  onSelect: (pin: PinData) => void;
  onDelete: (pin: PinData) => void;
}

export function PinsPanel({
  pins,
  expandedId,
  onSelect,
  onDelete,
  settings,
  message,
  reasons,
}: PinsPanelProps) {
  return (
    <MissionPanel title="Marked locations" darkHeader>
      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
        {settings}
        {message && (
          <p
            className="p-3 text-xs text-[color:var(--color-ink)]/80"
            role="status"
          >
            {message}
          </p>
        )}
        {reasons?.map((reason, index) => (
          <p
            key={index}
            className="px-3 pb-2 text-xs text-[color:var(--color-ink)]/80"
          >
            {reason}
          </p>
        ))}
        {pins.map((pin) => (
          <PersonPin
            key={pin.id}
            pin={pin}
            expanded={expandedId === pin.id}
            onSelect={onSelect}
            onDelete={onDelete}
          />
        ))}
      </div>
    </MissionPanel>
  );
}
