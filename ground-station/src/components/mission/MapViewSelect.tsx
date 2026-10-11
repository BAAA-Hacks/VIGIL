export const MAP_VIEWS = [
  { value: "topographic", label: "Topographic" },
  { value: "satellite", label: "Satellite" },
  { value: "street", label: "Street" },
] as const;

export type MapView = (typeof MAP_VIEWS)[number]["value"];

interface MapViewSelectProps {
  value: MapView;
  onChange: (view: MapView) => void;
}

export function MapViewSelect({ value, onChange }: MapViewSelectProps) {
  return (
    <div
      role="group"
      aria-label="Map view"
      className="ml-auto flex shrink-0 items-center gap-0.5 rounded-[7px] border border-[color:var(--color-paper)]/20 p-0.5"
    >
      {MAP_VIEWS.map((view) => (
        <button
          key={view.value}
          type="button"
          aria-pressed={value === view.value}
          onClick={() => onChange(view.value)}
          className={`h-7 rounded-[5px] px-1.5 text-[10px] focus-visible:outline-[color:var(--color-paper)] focus-visible:outline-offset-1 ${value === view.value ? "bg-[var(--color-paper)] font-medium text-[color:var(--color-ink)]" : "text-[color:var(--color-paper)]/80 hover:bg-[var(--color-paper)]/10"}`}
        >
          {view.label}
        </button>
      ))}
    </div>
  );
}
