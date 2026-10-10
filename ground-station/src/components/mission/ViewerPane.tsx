import type { ReactNode } from "react";
import { ArrowUpRight } from "lucide-react";

interface ViewerPaneProps {
  primary: boolean;
  kind: "map" | "thermal";
  onPromote: () => void;
  children: ReactNode;
}

export function ViewerPane({
  primary,
  kind,
  onPromote,
  children,
}: ViewerPaneProps) {
  const thermal = kind === "thermal";
  const placement = primary
    ? "inset-x-0 bottom-0 top-[42px] z-0"
    : "bottom-4 right-4 z-10 h-[190px] w-60 rounded-[3px] border border-[color:var(--color-ink)]/35 [&_.leaflet-control-zoom]:mt-10 max-[600px]:bottom-2.5 max-[600px]:right-2.5 max-[600px]:h-[145px] max-[600px]:w-[180px]";
  const background = thermal
    ? "bg-[var(--color-ink)]"
    : "bg-[var(--color-paper)]";

  return (
    <div className={"absolute overflow-hidden " + placement + " " + background}>
      {children}
      {!primary && (
        <button
          type="button"
          onClick={onPromote}
          aria-label={thermal ? "Expand thermal camera" : "Expand map"}
          className={
            "absolute top-0 z-[1100] flex items-start justify-end border-0 bg-transparent p-2.5 text-[10px] text-[color:var(--color-paper)] " +
            (thermal ? "inset-x-0 h-full w-full" : "right-0")
          }
        >
          <span className="flex items-center gap-1.5 rounded-[2px] border border-[color:var(--color-paper)]/20 bg-[var(--color-ink)]/95 px-2 py-1">
            {thermal ? "Thermal" : "Map"} <ArrowUpRight size={13} />
          </span>
        </button>
      )}
    </div>
  );
}
