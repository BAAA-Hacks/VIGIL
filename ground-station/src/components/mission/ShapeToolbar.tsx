import { Circle, Square, Triangle, Minus, UserRoundPlus } from "lucide-react";
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
  onAddPerson,
}: {
  disabled: boolean;
  onAddPerson: () => void;
  onAdd: (kind: PathShapeKind) => void;
}) {
  return (
    <div
      role="group"
      aria-label="Mission shapes"
      className="flex items-center gap-0.5 border-r border-[color:var(--color-paper)]/20 pr-2"
    >
      <span className="mr-1 text-[10px] text-[color:var(--color-paper)]/65 max-[400px]:sr-only">
        Route
      </span>
      <button
        type="button"
        draggable
        onDragStart={(event) => {
          event.dataTransfer.setData("application/x-vigil-person", "person");
          event.dataTransfer.effectAllowed = "copy";
        }}
        onClick={onAddPerson}
        aria-label="Add person manually"
        title="Drag person onto map · click to add at center"
        className="grid size-7 shrink-0 cursor-grab place-items-center rounded-[3px] text-[color:var(--color-paper)]/85 hover:bg-[var(--color-paper)]/15 focus-visible:outline-[color:var(--color-paper)] active:cursor-grabbing"
      >
        <UserRoundPlus size={17} aria-hidden="true" />
      </button>
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
          className="grid size-7 cursor-grab place-items-center rounded-[3px] text-[color:var(--color-paper)]/85 hover:bg-[var(--color-paper)]/15 hover:text-[color:var(--color-paper)] focus-visible:outline-[color:var(--color-paper)] active:cursor-grabbing"
        >
          <Icon size={17} strokeWidth={1.5} aria-hidden="true" />
        </button>
      ))}
    </div>
  );
}
