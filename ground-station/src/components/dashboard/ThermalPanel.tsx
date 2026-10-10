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
    <section className={`panel thermal-panel ${expanded ? "expanded" : ""}`}>
      <div className="panel-heading">
        <h2>
          <ScanLine size={18} /> Thermal view
        </h2>
        <span className="subtle">
          {frame ? `${frame.width} × ${frame.height}` : "Awaiting image"}
        </span>
        <button
          className="icon-button"
          aria-label={expanded ? "Exit expanded view" : "Expand thermal view"}
          onClick={() => onExpandedChange(!expanded)}
        >
          <Maximize2 size={17} />
        </button>
      </div>
      <div className="feed-label">
        <span className={stale ? "warning" : "mint"}>
          <i className={stale ? "dot warning-bg" : "dot"} />
          {status.toUpperCase()}
        </span>
        <span>{demo ? "MOCK SOURCE · 5 FPS" : "EXTERNAL SOURCE"}</span>
      </div>
      <ThermalImage
        frame={frame}
        detection={overlay ? current : null}
        demo={demo}
        palette={palette}
        hasPerson={scenario !== "empty"}
      />
      {stale && (
        <div className="stale-banner">
          <WifiOff size={15} />
          {disconnected ? "Feed disconnected." : "Frames are stale."} Detection
          results unavailable.
        </div>
      )}
      <div className="thermal-toolbar">
        <button disabled={!demo} onClick={() => togglePause()}>
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
          aria-label="Thermal palette"
          value={palette}
          onChange={(e) => onPaletteChange(e.target.value as ThermalPalette)}
          disabled={!demo}
        >
          <option value="iron">Iron palette</option>
          <option value="white">White hot</option>
        </select>
      </div>
      <div className="frame-footer">
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
