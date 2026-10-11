interface StatBoxProps {
  label: string;
  value: string;
}

export function StatBox({ label, value }: StatBoxProps) {
  return (
    <div className="flex min-w-0 flex-col justify-center gap-1">
      <span className="text-[11px] text-[color:var(--color-ink)]/80">
        {label}
      </span>
      <span className="text-sm font-medium tabular-nums [overflow-wrap:anywhere] text-[color:var(--color-ink)]">
        {value}
      </span>
    </div>
  );
}
