interface StatBoxProps {
  label: string;
  value: string;
  highlight?: boolean;
}
export function StatBox({ label, value, highlight = false }: StatBoxProps) {
  return (
    <div className="flex min-w-0 flex-col justify-center gap-2">
      <span className="text-[11px] text-[color:var(--color-ink)]/70">
        {label}
      </span>
      <span
        className={`text-[15px] font-medium tabular-nums [overflow-wrap:anywhere] ${highlight ? "text-[color:var(--color-ink)] font-semibold" : "text-[color:var(--color-ink)]"}`}
      >
        {value}
      </span>
    </div>
  );
}
