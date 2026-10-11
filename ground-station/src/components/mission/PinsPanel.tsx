"use client";
import type { ReactNode } from "react";
import { ListFilter, Check } from "lucide-react";
import type { PinData } from "../../types/mission";
import { MissionPanel } from "./MissionPanel";
import { PersonPin } from "./PersonPin";

export type TemperatureFilter = "all" | PinData["status"];
const FILTERS: { value: TemperatureFilter; label: string }[] = [
  { value: "all", label: "All people" },
  { value: "low", label: "Low temperature" },
  { value: "elevated", label: "High temperature" },
  { value: "normal", label: "Normal temperature" },
  { value: "unknown", label: "Unknown temperature" },
];

interface PinsPanelProps {
  settings?: ReactNode;
  message?: string;
  reasons?: string[];
  pins: PinData[];
  temperatureFilter: TemperatureFilter;
  onTemperatureFilterChange: (filter: TemperatureFilter) => void;
  expandedId: string | null;
  onSelect: (pin: PinData) => void;
  onDelete: (pin: PinData) => void;
}

export function PinsPanel({
  pins,
  temperatureFilter,
  onTemperatureFilterChange,
  expandedId,
  onSelect,
  onDelete,
  settings,
  message,
  reasons,
}: PinsPanelProps) {
  const shownPins = pins.filter(
    (pin) => temperatureFilter === "all" || pin.status === temperatureFilter,
  );
  return (
    <MissionPanel title="Marked locations" darkHeader>
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-[color:var(--color-ink)]/15 px-3 py-2">
        <details
          className="relative"
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              event.currentTarget.open = false;
              event.currentTarget.querySelector("summary")?.focus();
            }
          }}
        >
          <summary className="flex min-h-9 cursor-pointer list-none items-center gap-2 rounded-[4px] border border-[color:var(--color-ink)]/25 bg-[var(--color-paper)] px-3 text-xs hover:bg-[var(--color-ink)]/5 focus-visible:outline-2 focus-visible:outline-[color:var(--color-ink)] [&::-webkit-details-marker]:hidden">
            <ListFilter size={15} aria-hidden="true" />
            Filter
            {temperatureFilter !== "all" && (
              <span
                className="grid size-4 place-items-center rounded-full bg-[var(--color-blue)]/40 text-[10px]"
                aria-label="One active filter"
              >
                1
              </span>
            )}
          </summary>
          <div
            role="group"
            aria-label="Filter people"
            className="absolute left-0 top-full z-20 mt-1 w-48 rounded-[4px] border border-[color:var(--color-ink)]/20 bg-[var(--color-paper)] p-1 shadow-[0_4px_12px_color-mix(in_srgb,_var(--color-ink)_15%,_transparent)]"
          >
            {FILTERS.map((filter) => (
              <button
                key={filter.value}
                type="button"
                aria-pressed={temperatureFilter === filter.value}
                className="flex min-h-9 w-full items-center justify-between rounded-[3px] px-2 text-left text-xs hover:bg-[var(--color-ink)]/5 aria-pressed:bg-[var(--color-blue)]/20"
                onClick={(event) => {
                  onTemperatureFilterChange(filter.value);
                  event.currentTarget
                    .closest("details")
                    ?.removeAttribute("open");
                }}
              >
                {filter.label}
                {temperatureFilter === filter.value && (
                  <Check size={14} aria-hidden="true" />
                )}
              </button>
            ))}
          </div>
        </details>
        <span
          className="text-[11px] tabular-nums text-[color:var(--color-ink)]/75"
          role="status"
        >
          {shownPins.length} of {pins.length} shown
        </span>
      </div>
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
        {shownPins.length === 0 && (
          <p className="p-3 text-xs text-[color:var(--color-ink)]/75">
            {pins.length === 0
              ? "No people marked yet."
              : "No people match this filter. All locations remain visible on the map."}
          </p>
        )}
        {shownPins.map((pin) => (
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
