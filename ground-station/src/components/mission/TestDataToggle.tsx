interface TestDataToggleProps {
  enabled: boolean;
  onToggle: () => void;
  pinTestEnabled: boolean;
  onTogglePinTest: () => void;
}
export function TestDataToggle({
  enabled,
  onToggle,
  pinTestEnabled,
  onTogglePinTest,
}: TestDataToggleProps) {
  return (
    <div className="fixed bottom-2.5 right-3 z-[1200] flex gap-2">
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
        aria-label={
          enabled ? "Stop test data" : "Start test data"
        }
        title={
          enabled ? "Stop synthetic test data" : "Start synthetic test data"
        }
      >
        <span
          className={`size-[5px] rounded-full ${enabled ? "bg-[var(--color-blue)]" : "bg-[var(--color-ink)]/35"}`}
          aria-hidden="true"
        />
        {enabled ? "Stop test" : "Start test"}
      </button>
    </div>
  );
}
