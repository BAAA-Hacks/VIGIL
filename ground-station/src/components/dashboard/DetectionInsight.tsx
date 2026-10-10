import { Target } from "lucide-react";
import type { VigilFeed } from "../../hooks/useVigilFeed";
export function DetectionInsight({ feed }: { feed: VigilFeed }) {
  const { humans, stale, current, demo } = feed;
  return (
    <section className="panel detection-panel">
      <div className="panel-heading">
        <h2>
          <Target size={18} /> Detection insight
        </h2>
      </div>
      <div
        className={`detection-state ${humans.length && !stale ? "found" : ""}`}
      >
        <div className="target-icon">
          <Target size={30} />
        </div>
        <h3>
          {stale
            ? "Detection unavailable"
            : humans.length
              ? "Human detected"
              : "No target detected"}
        </h3>
        <p>
          {stale
            ? "Waiting for a fresh, matched frame."
            : humans.length
              ? "A human signature is visible in this frame."
              : "No human signatures in the current frame."}
        </p>
      </div>
      <div className="confidence">
        <span>
          Detection confidence
          <strong>
            {humans.length && !stale
              ? `${(humans[0].confidence * 100).toFixed(1)}%`
              : "—"}
          </strong>
        </span>
        <div className="progress">
          <i
            style={{
              width:
                humans.length && !stale
                  ? `${humans[0].confidence * 100}%`
                  : "0%",
            }}
          />
        </div>
      </div>
      <div className="insight-details">
        <div>
          <span>Classification</span>
          <b>{humans.length && !stale ? "Human" : "—"}</b>
        </div>
        <div>
          <span>Frame alignment</span>
          <b>{current ? "Matched" : "Waiting"}</b>
        </div>
        <div>
          <span>Source</span>
          <b>{demo ? "Simulated" : "External feed"}</b>
        </div>
      </div>
    </section>
  );
}
