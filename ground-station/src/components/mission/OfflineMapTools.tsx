import { useRef, useState } from "react";
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
  const button =
    "rounded-[4px] border border-[color:var(--color-ink)]/20 px-2 py-1.5 hover:bg-[var(--color-ink)]/5";
  return (
    <details className="absolute right-2 top-2 z-[1100] max-w-[calc(100%-16px)] rounded-[6px] border border-[color:var(--color-ink)]/20 bg-[var(--color-paper)] text-[11px] text-[color:var(--color-ink)]">
      <summary className="cursor-pointer px-2 py-2">Offline maps</summary>
      <div className="w-[220px] max-w-full space-y-2 border-t border-[color:var(--color-ink)]/15 p-2">
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
                error instanceof Error ? error.message : "Map download failed",
              );
            } finally {
              setBusy(false);
            }
          }}
        >
          {busy ? "Saving…" : "Save map area"}
        </button>
        <p>Import a terrain grid for elevation at new locations offline.</p>
        <button
          type="button"
          className={button}
          onClick={() => file.current?.click()}
        >
          Import terrain
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
        {message && <p role="status">{message}</p>}
      </div>
    </details>
  );
}
