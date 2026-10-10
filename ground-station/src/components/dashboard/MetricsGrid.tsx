import { Radio, Target, Activity, Eye } from "lucide-react";
import type { VigilFeed } from "../../hooks/useVigilFeed";
export function MetricsGrid({ feed }: { feed: VigilFeed }) {
  const { demo, stale, humans, current, status, count } = feed;
  return (
    <div className="metrics">
      <div className="metric">
        <span>
          <Radio size={17} /> FEED STATUS
        </span>
        <strong className={stale ? "warning" : "mint"}>
          <i className={stale ? "dot warning-bg" : "dot"} />
          {status}
        </strong>
        <small>
          {demo ? "Recorded-style simulation" : "External event input"}
        </small>
      </div>
      <div className="metric">
        <span>
          <Target size={17} /> HUMAN TARGETS
        </span>
        <strong>
          {stale ? "—" : humans.length.toString().padStart(2, "0")}
          <em>
            {humans.length && !stale
              ? "person detected"
              : stale
                ? "Feed unavailable"
                : "No target detected"}
          </em>
        </strong>
        <small>Current matched frame</small>
      </div>
      <div className="metric">
        <span>
          <Activity size={17} /> AI PROCESSING
        </span>
        <strong>
          {current?.processing_ms ?? "—"}
          <em>{current ? "ms" : "Waiting for data"}</em>
        </strong>
        <small>
          {demo ? "Simulated processing time" : "Reported by AI pipeline"}
        </small>
      </div>
      <div className="metric">
        <span>
          <Eye size={17} /> FRAMES RECEIVED
        </span>
        <strong>{count.toString().padStart(4, "0")}</strong>
        <small>Since feed started</small>
      </div>
    </div>
  );
}
