import { useEffect, useRef, useState } from "react";
import { dispatchVigil } from "../../lib/events";
import { gridTerrain, type TerrainGrid } from "../../lib/terrainGrid";

export function OfflineMapTools({
  save,
  openMission,
}: {
  openMission: () => Promise<void>;
  save: (progress: (done: number, total: number) => void) => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const file = useRef<HTMLInputElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const body = panel.current;
    const area = body?.closest("section");
    if (!body || !area) return;
    const measure = () => {
      const height = body.parentElement?.hasAttribute("open")
        ? body.getBoundingClientRect().height
        : 0;
      area.style.setProperty("--viewer-top", `${42 + height}px`);
    };
    const observer = new ResizeObserver(measure);
    observer.observe(body);
    const details = body.parentElement;
    details?.addEventListener("toggle", measure);
    measure();
    return () => {
      observer.disconnect();
      details?.removeEventListener("toggle", measure);
      area.style.removeProperty("--viewer-top");
    };
  }, []);
  const button =
    "rounded-[4px] border border-[color:var(--color-ink)]/20 px-2 py-1.5 hover:bg-[var(--color-ink)]/5";
  return (
    <details className="shrink-0 text-[11px] text-[color:var(--color-paper)]">
      <summary className="cursor-pointer rounded-[3px] px-2 py-2 hover:bg-[var(--color-paper)]/10">
        Offline maps
      </summary>
      <div
        ref={panel}
        className="absolute inset-x-0 top-[42px] z-20 grid max-h-[min(160px,35%)] grid-cols-3 items-start gap-x-4 gap-y-2 overflow-y-auto border-b border-[color:var(--color-ink)]/20 bg-[var(--color-paper)] p-3 text-[color:var(--color-ink)] max-[600px]:grid-cols-1"
      >
        <div className="space-y-2">
          <button
            type="button"
            className={button}
            onClick={async () => {
              try {
                await openMission();
                setMessage("Opened prepared mission area.");
              } catch (error) {
                setMessage(
                  error instanceof Error
                    ? error.message
                    : "Mission area unavailable",
                );
              }
            }}
          >
            Open saved mission area
          </button>
          <p className="text-[color:var(--color-ink)]/70">
            Open the prepared mission area saved on this computer.
          </p>
        </div>
        <div className="space-y-2">
          <p>
            Save the visible area in topographic, street, and satellite while
            online. Includes nearby zoom levels.
          </p>
          <button
            type="button"
            disabled={busy}
            className={button}
            onClick={async () => {
              setBusy(true);
              try {
                await save((done, total) =>
                  setMessage(`Saving map · ${done}/${total} tiles`),
                );
                setMessage("All three map layers saved on this computer.");
              } catch (error) {
                setMessage(
                  error instanceof Error
                    ? error.message
                    : "Map download failed",
                );
              } finally {
                setBusy(false);
              }
            }}
          >
            {busy ? "Saving…" : "Save map images"}
          </button>
        </div>
        <div className="space-y-2">
          <p>
            Load elevation measurements for offline person coordinates. Map
            images do not include these measurements.
          </p>
          <button
            type="button"
            className={button}
            onClick={() => file.current?.click()}
          >
            Import elevation grid
          </button>
          <input
            ref={file}
            type="file"
            accept=".json,application/json"
            className="sr-only"
            aria-label="Import offline terrain grid"
            onChange={async (event) => {
              const selected = event.target.files?.[0];
              if (!selected) return;
              try {
                if (selected.size > 8_000_000)
                  throw new Error("Terrain file is too large");
                const text = await selected.text();
                const grid = JSON.parse(text) as TerrainGrid;
                gridTerrain(grid);
                const response = await fetch("/api/offline-terrain", {
                  method: "POST",
                  body: text,
                  headers: { "Content-Type": "application/json" },
                });
                if (!response.ok) throw new Error("Invalid terrain grid");
                dispatchVigil("terrain", grid);
                setMessage("Terrain saved for offline elevation.");
              } catch (error) {
                setMessage(
                  error instanceof Error
                    ? error.message
                    : "Terrain import failed",
                );
              }
              event.target.value = "";
            }}
          />
        </div>
        {message && (
          <p className="col-span-full" role="status">
            {message}
          </p>
        )}
      </div>
    </details>
  );
}
