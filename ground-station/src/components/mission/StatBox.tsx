interface StatBoxProps {
  label: string;
  value: string;
  highlight?: boolean;
}
export function StatBox({ label, value, highlight = false }: StatBoxProps) {
  return (
    <div className="mission-stat">
      <span className="mission-stat-label">{label}</span>
      <span
        className={`mission-stat-value ${highlight ? "mission-stat-highlight" : ""}`}
      >
        {value}
      </span>
    </div>
  );
}
