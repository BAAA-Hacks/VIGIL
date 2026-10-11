interface TestDataToggleProps {
  enabled: boolean;
  /** Telemetry source reported by the bridge once connected ("pocket" = real drone). */
  source: string | null;
  onToggle: () => void;
  pinTestEnabled: boolean;
  onTogglePinTest: () => void;
  /** Shown only while ./replay.sh is running. */
  replay?: { available: boolean; paused: boolean; toggle: () => void };
}
export function TestDataToggle({
  enabled,
  source,
  onToggle,
  pinTestEnabled,
  onTogglePinTest,
  replay,
}: TestDataToggleProps) {
  return (
    <div className="fixed bottom-2.5 right-3 z-[1200] flex gap-2">
      {replay?.available && (
        <button
          type="button"
          onClick={replay.toggle}
          aria-pressed={replay.paused}
          title="Pause or resume the recorded flight replay (Space)"
          className="rounded-[3px] border border-[color:var(--color-ink)]/25 bg-[var(--color-paper)]/94 px-2 py-[5px] text-[10px] text-[color:var(--color-ink)]/70 hover:text-[color:var(--color-ink)]"
        >
          {replay.paused ? "Resume replay" : "Pause replay"}
        </button>
      )}
      <button
        type="button"
        onClick={onTogglePinTest}
        aria-pressed={pinTestEnabled}
        className="rounded-[3px] border border-[color:var(--color-ink)]/25 bg-[var(--color-paper)]/94 px-2 py-[5px] text-[10px] text-[color:var(--color-ink)]/70 hover:text-[color:var(--color-ink)]"
      >
        {pinTestEnabled ? "Stop pin test" : "Test pins"}
      </button>
      <button
        className="flex items-center gap-1.5 rounded-[3px] border border-[color:var(--color-ink)]/25 bg-[var(--color-paper)]/94 px-2 py-[5px] text-[10px] text-[color:var(--color-ink)]/70 hover:border-[color:var(--color-ink)]/65 hover:text-[color:var(--color-ink)] focus-visible:outline-2 focus-visible:outline-[color:var(--color-ink)] focus-visible:outline-offset-3"
        onClick={onToggle}
        aria-pressed={enabled}
        aria-label={enabled ? "Stop telemetry" : "Start telemetry"}
        title="Drone telemetry: live from the Pocket when TELEMETRY_SERIAL_PORT is set, otherwise synthetic"
      >
        <span
          className={`size-[5px] rounded-full ${enabled ? "bg-[var(--color-blue)]" : "bg-[var(--color-ink)]/35"}`}
          aria-hidden="true"
        />
        {!enabled
          ? "Start telemetry"
          : source === "pocket"
            ? "Stop drone"
            : source === "replay-track"
              ? "Stop flight replay"
              : "Stop test"}
      </button>
    </div>
  );
}
