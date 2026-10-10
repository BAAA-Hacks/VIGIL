import type { ReactNode } from "react";
import { Radio, Target, Activity, Eye } from "lucide-react";
import type { VigilFeed } from "../../hooks/useVigilFeed";

function MetricCard({
  icon,
  title,
  note,
  children,
}: {
  icon: ReactNode;
  title: string;
  note: string;
  children: ReactNode;
}) {
  return (
    <div className="rounded-lg border border-[color:var(--color-ink)]/25 bg-[var(--color-paper)] p-[18px] max-[1100px]:p-3.5">
      <span className="flex items-center gap-[9px] text-[9px] tracking-[1.1px] text-[color:var(--color-ink)]/70">
        {icon} {title}
      </span>
      {children}
      <small className="text-[10px] text-[color:var(--color-ink)]/70">
        {note}
      </small>
    </div>
  );
}

function MetricValue({
  value,
  description,
}: {
  value: ReactNode;
  description?: string;
}) {
  return (
    <strong className="mb-2 mt-[17px] flex items-center gap-[9px] text-[27px] [font-family:'Space_Grotesk',sans-serif] max-[1100px]:text-[23px] max-[550px]:flex-wrap">
      {value}
      {description && (
        <em className="text-[10px] font-normal not-italic text-[color:var(--color-ink)]/70 [font-family:'DM_Sans',sans-serif] max-[1100px]:text-[9px]">
          {description}
        </em>
      )}
    </strong>
  );
}

export function MetricsGrid({ feed }: { feed: VigilFeed }) {
  const { demo, stale, humans, current, status, count } = feed;
  return (
    <div className="mb-6 grid grid-cols-4 gap-3.5 max-[1100px]:gap-2.5 max-[850px]:grid-cols-2">
      <MetricCard
        icon={<Radio size={17} />}
        title="FEED STATUS"
        note={demo ? "Recorded-style simulation" : "External event input"}
      >
        <strong
          className={
            "mb-2 mt-[17px] flex items-center gap-[9px] text-[19px] [font-family:'Space_Grotesk',sans-serif] max-[550px]:flex-wrap max-[550px]:text-base " +
            (stale
              ? "text-[color:var(--color-peach)]"
              : "text-[color:var(--color-ink)]")
          }
        >
          <i
            className={
              "inline-block size-1.5 rounded-full " +
              (stale ? "bg-[var(--color-peach)]" : "bg-[var(--color-ink)]")
            }
          />
          {status}
        </strong>
      </MetricCard>
      <MetricCard
        icon={<Target size={17} />}
        title="HUMAN TARGETS"
        note="Current matched frame"
      >
        <MetricValue
          value={stale ? "—" : humans.length.toString().padStart(2, "0")}
          description={
            humans.length && !stale
              ? "person detected"
              : stale
                ? "Feed unavailable"
                : "No target detected"
          }
        />
      </MetricCard>
      <MetricCard
        icon={<Activity size={17} />}
        title="AI PROCESSING"
        note={demo ? "Simulated processing time" : "Reported by AI pipeline"}
      >
        <MetricValue
          value={current?.processing_ms ?? "—"}
          description={current ? "ms" : "Waiting for data"}
        />
      </MetricCard>
      <MetricCard
        icon={<Eye size={17} />}
        title="FRAMES RECEIVED"
        note="Since feed started"
      >
        <MetricValue value={count.toString().padStart(4, "0")} />
      </MetricCard>
    </div>
  );
}
