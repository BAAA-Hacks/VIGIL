import type { ReactNode } from "react";
import { ArrowUpRight, Minus, PictureInPicture2 } from "lucide-react";

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
  const thermal = kind === "thermal";
  const label = thermal ? "Thermal camera" : "Map";
  const placement = primary
    ? "inset-x-0 bottom-0 top-[42px] z-0"
    : "bottom-4 right-4 z-10 h-[190px] w-60 rounded-[3px] border border-[color:var(--color-ink)]/35 [&_.leaflet-control-zoom]:mt-10 max-[600px]:bottom-2.5 max-[600px]:right-2.5 max-[600px]:h-[145px] max-[600px]:w-[180px]";
  const background = thermal
    ? "bg-[var(--color-ink)]"
    : "bg-[var(--color-paper)]";
  const controlStyle =
    "flex items-center gap-1.5 rounded-[2px] border border-[color:var(--color-paper)]/20 bg-[var(--color-ink)]/95 px-2 py-1 text-[10px] text-[color:var(--color-paper)] hover:bg-[var(--color-ink)] focus-visible:outline-[var(--color-paper)]";

  return (
    <>
      <div
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
          <div className="absolute right-2.5 top-2.5 z-[1100] flex gap-1">
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
          className={
            "absolute bottom-4 right-4 z-[1100] max-[600px]:bottom-2.5 max-[600px]:right-2.5 " +
            controlStyle
          }
        >
          <PictureInPicture2 size={13} /> Show {thermal ? "thermal" : "map"}
        </button>
      )}
    </>
  );
}
