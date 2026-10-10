import { useRef, useState, type ReactNode } from "react";
import { ArrowUpRight, Minus, PictureInPicture2, Grip } from "lucide-react";

interface ViewerPaneProps {
  primary: boolean;
  kind: "map" | "thermal";
  minimized: boolean;
  onMinimize: () => void;
  onRestore: () => void;
  onPromote: () => void;
  children: ReactNode;
}

export function ViewerPane({
  primary,
  kind,
  minimized,
  onMinimize,
  onRestore,
  onPromote,
  children,
}: ViewerPaneProps) {
  const [size, setSize] = useState<{ width: number; height: number } | null>(
    null,
  );
  const drag = useRef<{
    x: number;
    y: number;
    width: number;
    height: number;
    maxWidth: number;
    maxHeight: number;
  } | null>(null);
  const thermal = kind === "thermal";
  const label = thermal ? "Thermal camera" : "Map";
  const placement = primary
    ? "inset-x-0 bottom-0 top-[42px] z-0"
    : "bottom-6 right-2 z-10 h-[160px] w-[192px] rounded-[12px] border border-[color:var(--color-ink)]/35 pt-7 max-[600px]:h-[127px] max-[600px]:w-[150px]";
  const background = thermal
    ? "bg-[var(--color-ink)]"
    : "bg-[var(--color-paper)]";
  const controlStyle =
    "flex items-center gap-1.5 rounded-[2px] border border-[color:var(--color-paper)]/20 bg-[var(--color-ink)]/95 px-1.5 py-1 text-[10px] text-[color:var(--color-paper)] hover:bg-[var(--color-ink)] focus-visible:outline-[var(--color-paper)]";

  return (
    <>
      <div
        style={
          !primary && size
            ? {
                width: `min(${size.width}px, calc(100% - 16px))`,
                height: `min(${size.height}px, calc(100% - 74px))`,
              }
            : undefined
        }
        data-inset={!primary && !minimized ? "" : undefined}
        className={
          "absolute overflow-hidden " +
          placement +
          " " +
          background +
          (!primary && minimized ? " hidden" : "")
        }
      >
        {children}
        {!primary && (
          <button
            type="button"
            aria-label={`Resize ${label.toLowerCase()} window`}
            title="Drag to resize · arrow keys adjust size"
            className="absolute left-0 top-0 z-[1200] grid size-7 touch-none cursor-nwse-resize place-items-center text-[color:var(--color-paper)]/70 hover:text-[color:var(--color-paper)] focus-visible:outline-[color:var(--color-paper)]"
            onPointerDown={(event) => {
              event.preventDefault();
              const pane = event.currentTarget.parentElement!;
              const bounds = pane.getBoundingClientRect();
              const parent = pane.parentElement!.getBoundingClientRect();
              drag.current = {
                x: event.clientX,
                y: event.clientY,
                width: bounds.width,
                height: bounds.height,
                maxWidth: parent.width - 16,
                maxHeight: parent.height - 74,
              };
              event.currentTarget.setPointerCapture(event.pointerId);
            }}
            onPointerMove={(event) => {
              const start = drag.current;
              if (!start) return;
              setSize({
                width: Math.min(
                  start.maxWidth,
                  Math.max(150, start.width + start.x - event.clientX),
                ),
                height: Math.min(
                  start.maxHeight,
                  Math.max(120, start.height + start.y - event.clientY),
                ),
              });
            }}
            onPointerUp={(event) => {
              drag.current = null;
              event.currentTarget.releasePointerCapture(event.pointerId);
            }}
            onPointerCancel={() => {
              drag.current = null;
            }}
            onLostPointerCapture={() => {
              drag.current = null;
            }}
            onKeyDown={(event) => {
              if (
                !["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(
                  event.key,
                )
              )
                return;
              event.preventDefault();
              const pane = event.currentTarget.parentElement!;
              const bounds = pane.getBoundingClientRect();
              const parent = pane.parentElement!.getBoundingClientRect();
              setSize({
                width: Math.min(
                  parent.width - 16,
                  Math.max(
                    150,
                    bounds.width +
                      (event.key === "ArrowLeft"
                        ? 16
                        : event.key === "ArrowRight"
                          ? -16
                          : 0),
                  ),
                ),
                height: Math.min(
                  parent.height - 74,
                  Math.max(
                    120,
                    bounds.height +
                      (event.key === "ArrowUp"
                        ? 16
                        : event.key === "ArrowDown"
                          ? -16
                          : 0),
                  ),
                ),
              });
            }}
          >
            <Grip size={13} aria-hidden="true" />
          </button>
        )}
        {!primary && (
          <div className="absolute inset-x-0 top-0 z-[1100] flex h-7 items-center justify-end gap-1 border-b border-[color:var(--color-paper)]/15 bg-[var(--color-ink)] px-1">
            <button
              type="button"
              onClick={onMinimize}
              aria-label={`Minimize ${label.toLowerCase()}`}
              title={`Minimize ${label.toLowerCase()}`}
              className={controlStyle}
            >
              <Minus size={13} />
            </button>
            <button
              type="button"
              onClick={onPromote}
              aria-label={`Expand ${label.toLowerCase()}`}
              className={controlStyle}
            >
              {thermal ? "Thermal" : "Map"} <ArrowUpRight size={13} />
            </button>
          </div>
        )}
      </div>
      {!primary && minimized && (
        <button
          type="button"
          onClick={onRestore}
          aria-label={`Restore ${label.toLowerCase()}`}
          className={"absolute bottom-6 right-2 z-[1100] " + controlStyle}
        >
          <PictureInPicture2 size={13} /> Show {thermal ? "thermal" : "map"}
        </button>
      )}
    </>
  );
}

