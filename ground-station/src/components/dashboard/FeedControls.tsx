import { Settings2 } from "lucide-react";
import type { FeedMode, DemoScenario } from "../../types/vigil";
import type { VigilFeed } from "../../hooks/useVigilFeed";
export function FeedControls({ feed }: { feed: VigilFeed }) {
  const { mode, changeMode, demo, scenario, setScenario } = feed;
  return (
    <section className=" border border-[color:var(--color-ink)]/25 rounded-[9px] bg-[var(--color-paper)] overflow-hidden  [&_>_label]:block [&_>_label]:px-5 [&_>_label]:pt-4 [&_>_label]:text-[10px] [&_>_label]:text-[color:var(--color-ink)]/70 [&_p]:text-[10px] [&_p]:my-[18px] [&_p]:mx-5 [&_p]:text-[color:var(--color-ink)]/70">
      <div className=" flex items-center gap-3 h-[58px] border-b border-[color:var(--color-ink)]/25 px-[19px]">
        <h2 className="flex items-center gap-[9px] text-[13px] font-medium m-0 [&_svg]:text-[color:var(--color-ink)]/70">
          <Settings2 size={17} /> Feed
        </h2>
      </div>
      <label>
        Input source
        <select
          className="block w-full mt-2 rounded-[5px] border border-[color:var(--color-ink)]/25 bg-[var(--color-paper)] p-[9px] text-[color:var(--color-ink)]"
          value={mode}
          onChange={(e) => changeMode(e.target.value as FeedMode)}
        >
          <option value="demo">Demo simulation</option>
          <option value="live">Live integration</option>
        </select>
      </label>
      {demo && (
        <label>
          Demo scenario
          <select
            className="block w-full mt-2 rounded-[5px] border border-[color:var(--color-ink)]/25 bg-[var(--color-paper)] p-[9px] text-[color:var(--color-ink)]"
            value={scenario}
            onChange={(e) => setScenario(e.target.value as DemoScenario)}
          >
            <option value="human">Human detected</option>
            <option value="">No target</option>
            <option value="disconnected">Disconnected feed</option>
          </select>
        </label>
      )}
      <p className="text-xs leading-relaxed text-[color:var(--color-ink)]/70">
        Flight telemetry is unavailable. Connect real telemetry before
        displaying vehicle data.
      </p>
    </section>
  );
}
