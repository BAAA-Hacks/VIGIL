import type { useMissionPlanner } from "../../hooks/useMissionPlanner";
type Planner = ReturnType<typeof useMissionPlanner>;

export function MissionPathPanel({ planner }: { planner: Planner }) {
  const { selected, shapes, sending } = planner;
  if (!shapes.length) return null;
  const input =
    "mt-1.5 min-h-8 min-w-0 w-full rounded-[4px] border border-[color:var(--color-ink)]/20 bg-[var(--color-paper)] px-2 py-1.5 text-xs font-normal tabular-nums outline-none transition-colors focus:border-[color:var(--color-ink)] focus:ring-2 focus:ring-[var(--color-blue)]/40";
  return (
    <details className="group absolute top-2 left-2 z-[1100] max-h-[calc(100%-48px)] w-fit max-w-[calc(100%-16px)] overflow-y-auto rounded-[4px] open:static open:order-first open:h-full open:max-h-none open:w-full open:max-w-none open:rounded-none open:shadow-none border border-[color:var(--color-ink)]/25 bg-[var(--color-paper)] text-xs text-[color:var(--color-ink)] shadow-[0_4px_16px_color-mix(in_srgb,_var(--color-ink)_18%,_transparent)]">
      <summary className="cursor-pointer bg-[var(--color-ink)] px-3 py-2.5 font-medium text-[color:var(--color-paper)] marker:text-[color:var(--color-blue)]">
        Auton pathing{" "}
        <span className="ml-2 rounded-[3px] bg-[var(--color-paper)]/15 px-2 py-1 text-[10px] font-normal tabular-nums">
          {planner.count} points
        </span>
      </summary>
      {!planner.configured && (
        <p className="mx-3 mt-2 rounded-[4px] border border-[color:var(--color-ink)]/10 bg-[var(--color-yellow)]/25 px-3 py-2 leading-relaxed">
          INAV upload connection is not configured. Use XML export for now.
        </p>
      )}
      <fieldset
        disabled={sending}
        className="space-y-3 p-3 disabled:opacity-60"
      >
        <div
          className="flex flex-wrap gap-1.5"
          role="group"
          aria-label="Route shapes"
        >
          {shapes.map((shape, i) => (
            <button
              key={shape.id}
              type="button"
              aria-pressed={selected?.id === shape.id}
              onClick={() => planner.select(shape.id)}
              className={`min-h-8 rounded-[4px] border px-2.5 py-1.5 capitalize transition-colors ${selected?.id === shape.id ? "border-[color:var(--color-ink)]/35 bg-[var(--color-blue)]/40 font-medium" : "border-[color:var(--color-ink)]/15 bg-transparent hover:bg-[var(--color-ink)]/5"}`}
            >
              {i + 1}. {shape.kind}
            </button>
          ))}
        </div>
        {selected && (
          <div className="flex items-end gap-2">
            <label className="grow font-medium">
              Size (m)
              <input
                type="number"
                min="2"
                max="500"
                value={Math.round(selected.sizeM * 10) / 10}
                onChange={(e) => {
                  const sizeM = Number(e.target.value);
                  if (Number.isFinite(sizeM) && sizeM >= 2 && sizeM <= 500)
                    planner.update({ ...selected, sizeM });
                }}
                className={input}
              />
            </label>
            <button
              type="button"
              onClick={planner.remove}
              className="min-h-8 rounded-[4px] border border-[color:var(--color-ink)]/20 px-3 py-2 transition-colors hover:border-[color:var(--color-pink)]/40 hover:bg-[var(--color-pink)]/5"
            >
              Remove
            </button>
          </div>
        )}
        <div className="grid grid-cols-2 gap-2 border-t border-[color:var(--color-ink)]/15 pt-3">
          <label className="font-medium">
            Altitude (m)
            <input
              type="number"
              step="1"
              value={planner.altitude}
              onChange={(e) => planner.setAltitude(e.target.value)}
              className={input}
            />
          </label>
          <label className="font-medium">
            Speed (m/s)
            <input
              type="number"
              min="0.1"
              max="20"
              step="0.1"
              value={planner.speed}
              onChange={(e) => planner.setSpeed(e.target.value)}
              className={input}
            />
          </label>
        </div>
        <label className="block font-medium">
          Altitude reference
          <select
            value={planner.reference}
            onChange={(e) =>
              planner.setReference(e.target.value === "amsl" ? "amsl" : "home")
            }
            className={input}
          >
            <option value="home">Above home</option>
            <option value="amsl">Above sea level</option>
          </select>
        </label>
        <p className="text-[11px] leading-relaxed text-[color:var(--color-ink)]/75">
          Ends at the last point and holds. Altitude is{" "}
          {planner.reference === "home"
            ? "relative to home, not terrain clearance"
            : "above sea level, not terrain clearance"}
          .
        </p>
        <label className="flex items-start gap-2.5 rounded-[4px] border border-[color:var(--color-ink)]/15 bg-[var(--color-ink)]/5 p-3 text-[11px] leading-relaxed">
          <input
            type="checkbox"
            checked={planner.takeoverConfirmed}
            onChange={(e) => planner.setTakeoverConfirmed(e.target.checked)}
            className="mt-0.5 size-3.5 shrink-0"
          />
          Transmitter switch tested: leaving NAV WP restores pilot control.
        </label>
        <div className="grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={planner.exportXml}
            className="min-h-10 rounded-[4px] border border-[color:var(--color-ink)]/25 px-3 py-2 font-medium transition-colors hover:bg-[var(--color-ink)]/5"
          >
            Export XML
          </button>
          <button
            type="button"
            disabled={!planner.configured || !planner.takeoverConfirmed}
            onClick={planner.send}
            className="min-h-10 rounded-[4px] bg-[var(--color-ink)] px-3 py-2 font-medium text-[color:var(--color-paper)] transition-colors enabled:hover:bg-[var(--color-ink)]/85"
          >
            {sending ? "Sending…" : "Send to INAV"}
          </button>
        </div>
      </fieldset>
      <p
        role="status"
        className="px-3 pb-2 text-[11px] leading-relaxed text-[color:var(--color-ink)]/80"
      >
        {planner.message}
      </p>
      <p className="border-t border-[color:var(--color-ink)]/15 bg-[var(--color-ink)]/5 px-3 py-2 text-[11px] leading-relaxed text-[color:var(--color-ink)]/75">
        Pilot control: use your transmitter’s mode switch at any time. Upload
        does not arm or start flight.
      </p>
    </details>
  );
}
