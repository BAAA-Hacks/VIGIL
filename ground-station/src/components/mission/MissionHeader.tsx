export function MissionHeader() {
  return (
    <header className="flex h-[72px] min-h-[72px] w-full items-center justify-between gap-4 border-b border-[color:var(--color-ink)] bg-[var(--color-ink)] px-6 max-[600px]:px-4">
      <div className="flex items-center gap-[18px] max-[600px]:gap-2.5">
        <a
          href="/"
          className="text-[19px] font-bold tracking-[1px] text-[color:var(--color-paper)] no-underline"
        >
          VIGIL
        </a>
        <span className="h-5 w-px bg-[var(--color-paper)]/30 max-[600px]:hidden" />
        <span className="text-[13px] text-[color:var(--color-paper)]/75 max-[600px]:max-w-[135px] max-[600px]:text-[11px] max-[600px]:leading-normal">
          Search & rescue / Ground station
        </span>
      </div>
    </header>
  );
}
