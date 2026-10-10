import { Circle, Square, Triangle, Minus } from "lucide-react";
import { SHAPE_POINTS, type PathShapeKind } from "../../lib/missionPath";

const SHAPES = [
  { kind: "circle", label: "Circle", Icon: Circle },
  { kind: "square", label: "Square", Icon: Square },
  { kind: "triangle", label: "Triangle", Icon: Triangle },
  { kind: "line", label: "Line", Icon: Minus },
] as const;

export function ShapeToolbar({
  disabled,
  onAdd,
}: {
  disabled: boolean;
  onAdd: (kind: PathShapeKind) => void;
}) {
  return (
    <div
      role="group"
      aria-label="Mission shapes"
      className="absolute right-3 top-[54px] z-[1100] flex flex-col rounded-[4px] border border-[color:var(--color-ink)]/25 bg-[var(--color-paper)] p-1 shadow-[0_2px_6px_color-mix(in_srgb,_var(--color-ink)_15%,_transparent)]"
    >
      {SHAPES.map(({ kind, label, Icon }) => (
        <button
          key={kind}
          type="button"
          disabled={disabled}
          draggable={!disabled}
          onDragStart={(event) => {
            event.dataTransfer.setData("application/x-vigil-shape", kind);
            event.dataTransfer.effectAllowed = "copy";
          }}
          onClick={() => onAdd(kind)}
          aria-label={`Add ${label.toLowerCase()}, ${SHAPE_POINTS[kind]} waypoints`}
          title={`Drag ${label.toLowerCase()} onto map · ${SHAPE_POINTS[kind]} points`}
          className="grid size-10 cursor-grab place-items-center rounded-[2px] text-[color:var(--color-ink)] hover:bg-[var(--color-ink)]/10 active:cursor-grabbing"
        >
          <Icon size={21} strokeWidth={1.5} aria-hidden="true" />
        </button>
      ))}
    </div>
  );
}
