import { Settings2 } from "lucide-react";
import type { FeedMode, DemoScenario } from "../../types/vigil";
import type { VigilFeed } from "../../hooks/useVigilFeed";
export function FeedControls({ feed }: { feed: VigilFeed }) {
  const { mode, changeMode, demo, scenario, setScenario } = feed;
  return (
    <section className="panel controls">
      <div className="panel-heading">
        <h2>
          <Settings2 size={17} /> Feed controls
        </h2>
      </div>
      <label>
        Input source
        <select
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
            value={scenario}
            onChange={(e) => setScenario(e.target.value as DemoScenario)}
          >
            <option value="human">Human detected</option>
            <option value="empty">No target</option>
            <option value="disconnected">Disconnected feed</option>
          </select>
        </label>
      )}
      <p>
        Flight telemetry is unavailable. Connect real telemetry before
        displaying vehicle data.
      </p>
    </section>
  );
}
