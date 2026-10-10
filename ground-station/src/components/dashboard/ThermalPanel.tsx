import { ScanLine, Maximize2, WifiOff, Play, Pause } from "lucide-react";
import type { ThermalPalette } from "../../types/vigil";
import type { VigilFeed } from "../../hooks/useVigilFeed";
import { ThermalImage } from "./ThermalImage";
export function ThermalPanel({
  feed,
  palette,
  onPaletteChange,
  overlay,
  onOverlayChange,
  expanded,
  onExpandedChange,
}: {
  feed: VigilFeed;
  palette: ThermalPalette;
  onPaletteChange: (value: ThermalPalette) => void;
  overlay: boolean;
  onOverlayChange: (value: boolean) => void;
  expanded: boolean;
  onExpandedChange: (value: boolean) => void;
}) {
  const {
    frame,
    current,
    demo,
    scenario,
    stale,
    disconnected,
    status,
    paused,
    togglePause,
    received,
    age,
  } = feed;
  return (
    <section
      className={` border border-[color:var(--color-ink)]/25 rounded-[9px] bg-[var(--color-paper)] ${expanded ? " fixed inset-5 z-[20] overflow-auto max-w-[1000px] m-auto" : "overflow-hidden"}`}
    >
      <div className=" flex items-center gap-3 h-[58px] border-b border-[color:var(--color-ink)]/25 px-[19px]">
        <h2 className="flex items-center gap-[9px] text-[13px] font-medium m-0 [&_svg]:text-[color:var(--color-ink)]/70">
          <ScanLine size={18} /> Thermal view
        </h2>
        <span className=" text-[10px] text-[color:var(--color-ink)]/70 ml-auto">
          {frame ? `${frame.width} × ${frame.height}` : "Awaiting image"}
        </span>
        <button
          className="inline-flex items-center justify-center gap-2  bg-transparent border-0 text-[color:var(--color-ink)]/70 p-[5px]"
          aria-label={expanded ? "Exit expanded view" : "Expand thermal view"}
          onClick={() => onExpandedChange(!expanded)}
        >
          <Maximize2 size={17} />
        </button>
      </div>
      <div className=" flex items-center justify-between py-3.5 px-5 text-[8px] tracking-[1.3px] text-[color:var(--color-ink)]/70 [&_.dot]:mr-1.5 max-[550px]:p-3">
        <span
          className={
            stale
              ? " text-[color:var(--color-peach)]"
              : " text-[color:var(--color-ink)]"
          }
        >
          <i
            className={
              stale
                ? "dot inline-block w-[6px] h-[6px] rounded-full bg-[var(--color-peach)] shadow-[0_0_9px_color-mix(in_srgb,_var(--color-ink)_25%,_transparent)]"
                : "dot inline-block w-[6px] h-[6px] rounded-full bg-[var(--color-ink)] shadow-[0_0_9px_color-mix(in_srgb,_var(--color-ink)_25%,_transparent)]"
            }
          />
          {status.toUpperCase()}
        </span>
        <span>{demo ? "MOCK SOURCE · 5 FPS" : "EXTERNAL SOURCE"}</span>
      </div>
      <ThermalImage
        expanded={expanded}
        frame={frame}
        detection={overlay ? current : null}
        demo={demo}
        palette={palette}
        hasPerson={scenario !== "empty"}
      />
      {stale && (
        <div className=" flex items-center gap-2 text-[color:var(--color-peach)] bg-[var(--color-peach)]/15 py-3 px-5 text-[11px]">
          <WifiOff size={15} />
          {disconnected ? "Feed disconnected." : "Frames are stale."} Detection
          results unavailable.
        </div>
      )}
      <div className=" flex items-center gap-[18px] px-5 py-[17px] [&_button]:bg-[var(--color-paper)] [&_button]:border [&_button]:border-[color:var(--color-ink)]/25 [&_button]:text-[color:var(--color-ink)] [&_button]:rounded-[4px] [&_button]:text-[11px] [&_button]:px-2.5 [&_button]:py-[7px] [&_label]:flex [&_label]:items-center [&_label]:gap-1.5 [&_label]:text-[color:var(--color-ink)]/70 [&_label]:text-[10px] [&_select]:ml-auto [&_select]:text-[10px] [&_select]:w-auto max-[1100px]:gap-2 max-[550px]:flex-wrap max-[550px]:[&_select]:ml-0 max-[550px]:py-3.5 max-[550px]:px-3">
        <button
          className="inline-flex items-center justify-center gap-2"
          disabled={!demo}
          onClick={() => togglePause()}
        >
          {paused ? <Play size={16} /> : <Pause size={16} />}{" "}
          {paused ? "Resume" : "Pause"}
        </button>
        <label>
          <input
            type="checkbox"
            checked={overlay}
            onChange={(e) => onOverlayChange(e.target.checked)}
          />{" "}
          Detection overlays
        </label>
        <select
          className="block w-full mt-2 rounded-[5px] border border-[color:var(--color-ink)]/25 bg-[var(--color-paper)] p-[9px] text-[color:var(--color-ink)]"
          aria-label="Thermal palette"
          value={palette}
          onChange={(e) => onPaletteChange(e.target.value as ThermalPalette)}
          disabled={!demo}
        >
          <option value="iron">Iron palette</option>
          <option value="white">White hot</option>
        </select>
      </div>
      <div className=" border-t border-[color:var(--color-ink)]/25 py-3.5 px-5 flex justify-between text-[color:var(--color-ink)]/70 text-[8px] tracking-[0.7px] [&_b]:text-[color:var(--color-ink)] [&_b]:font-normal [&_b]:ml-1.5 [&_b]:tracking-[0] max-[550px]:flex-wrap max-[550px]:gap-2.5">
        <span>
          FRAME <b>{frame?.frame_id ?? "—"}</b>
        </span>
        <span>
          LAST RECEIVED{" "}
          <b>{received ? `${(age / 1000).toFixed(1)}s ago` : "Never"}</b>
        </span>
      </div>
    </section>
  );
}
