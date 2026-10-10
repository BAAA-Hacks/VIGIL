import { Target } from "lucide-react";
import type { VigilFeed } from "../../hooks/useVigilFeed";
export function DetectionInsight({ feed }: { feed: VigilFeed }) {
  const { humans, stale, current, demo } = feed;
  return (
    <section className=" border border-[color:var(--color-ink)]/25 rounded-[9px] bg-[var(--color-paper)] overflow-hidden ">
      <div className=" flex items-center gap-3 h-[58px] border-b border-[color:var(--color-ink)]/25 px-[19px]">
        <h2 className="flex items-center gap-[9px] text-[13px] font-medium m-0 [&_svg]:text-[color:var(--color-ink)]/70">
          <Target size={18} /> Detection insight
        </h2>
      </div>
      <div
        className={` text-center px-5 pb-5 pt-6 [&_h3]:[font-family:'Space_Grotesk',_sans-serif] [&_h3]:text-[20px] [&_h3]:mb-2 [&_p]:text-[11px] ${humans.length && !stale ? " [&_.target-icon]:bg-[var(--color-ink)]/8 [&_.target-icon]:border-[color:var(--color-ink)]/25 [&_.target-icon]:text-[color:var(--color-ink)] [&_h3]:text-[color:var(--color-ink)]" : ""}`}
      >
        <div className="target-icon w-[60px] h-[60px] mx-auto mb-4 grid place-items-center bg-[var(--color-paper)] border border-[color:var(--color-ink)]/25 rounded-full text-[color:var(--color-ink)]/70">
          <Target size={30} />
        </div>
        <h3>
          {stale
            ? "Detection unavailable"
            : humans.length
              ? "Human detected"
              : "No target detected"}
        </h3>
        <p className="text-xs leading-relaxed text-[color:var(--color-ink)]/70">
          {stale
            ? "Waiting for a fresh, matched frame."
            : humans.length
              ? "A human signature is visible in this frame."
              : "No human signatures in the current frame."}
        </p>
      </div>
      <div className=" px-5 pb-5 [&_>_span]:flex [&_>_span]:justify-between [&_>_span]:text-[10px] [&_>_span]:text-[color:var(--color-ink)]/70 [&_strong]:text-[color:var(--color-ink)]">
        <span>
          Detection confidence
          <strong>
            {humans.length && !stale
              ? `${(humans[0].confidence * 100).toFixed(1)}%`
              : "—"}
          </strong>
        </span>
        <div className=" h-[5px] bg-[var(--color-ink)]/20 rounded-[4px] mt-3 overflow-hidden [&_i]:block [&_i]:h-full [&_i]:bg-[var(--color-ink)] [&_i]:[transition:width_0.3s]">
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
      <div className=" border-t border-[color:var(--color-ink)]/25 py-4 px-5 [&_div]:flex [&_div]:justify-between [&_div]:text-[10px] [&_div]:py-[7px] [&_div]:text-[color:var(--color-ink)]/70 [&_b]:font-normal [&_b]:text-[color:var(--color-ink)]">
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
