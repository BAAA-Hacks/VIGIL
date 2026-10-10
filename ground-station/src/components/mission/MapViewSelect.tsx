export const MAP_VIEWS = [
  { value: "street", label: "Street" },
  { value: "topographic", label: "Topographic" },
  { value: "satellite", label: "Satellite" },
] as const;

export type MapView = (typeof MAP_VIEWS)[number]["value"];

interface MapViewSelectProps {
  value: MapView;
  onChange: (view: MapView) => void;
}

export function MapViewSelect({ value, onChange }: MapViewSelectProps) {
  return (
    <select
      className="ml-auto w-auto rounded-[5px] border border-[color:var(--color-ink)]/20 bg-[var(--color-paper)] px-2 py-1 text-[11px] text-[color:var(--color-ink)]"
      aria-label="Map view"
      value={value}
      onChange={(event) => {
        const view = MAP_VIEWS.find(
          (option) => option.value === event.target.value,
        );
        if (view) onChange(view.value);
      }}
    >
      {MAP_VIEWS.map((view) => (
        <option key={view.value} value={view.value}>
          {view.label}
        </option>
      ))}
    </select>
  );
}
