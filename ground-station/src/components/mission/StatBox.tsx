interface StatBoxProps {
  label: string;
  value: string;
}
export function StatBox({ label, value }: StatBoxProps) {
  return (
    <div className="flex min-w-0 flex-col justify-center gap-2">
      <span className="text-xs text-[color:var(--color-ink)]/80">{label}</span>
      <span className="text-[15px] font-medium tabular-nums [overflow-wrap:anywhere] text-[color:var(--color-ink)]">
        {value}
      </span>
    </div>
  );
}
