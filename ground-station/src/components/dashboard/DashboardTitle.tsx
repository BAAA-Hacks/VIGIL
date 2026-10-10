import { Play } from "lucide-react";
export function DashboardTitle({ onStartDemo }: { onStartDemo: () => void }) {
  return (
    <div className=" flex items-center justify-between pt-[34px] pb-[27px] max-[550px]:py-[26px] max-[550px]:items-start max-[550px]:gap-2">
      <div>
        <div className=" text-[9px] tracking-[2px] text-[color:var(--color-ink)]/70 max-[550px]:text-[7px] max-[550px]:tracking-[1px]">
          VISUAL INTELLIGENCE & GEOLOCATION
        </div>
        <h1 className="[&_span]:text-[color:var(--color-ink)] [font-family:'Space_Grotesk',_sans-serif] text-[34px] tracking-[-1.3px] my-2.5 mx-0 max-[850px]:text-[29px] max-[550px]:text-[26px]">
          Eyes on the field<span>.</span>
        </h1>
        <p className="text-xs leading-relaxed text-[color:var(--color-ink)]/70">
          Thermal awareness. Clear decisions.
        </p>
      </div>
      <button
        className="inline-flex items-center justify-center gap-2 inline-flex items-center justify-center gap-2 rounded-md bg-[var(--color-ink)] px-[18px] py-3 text-xs font-bold text-[color:var(--color-paper)] hover:bg-[var(--color-ink)]/90 max-[550px]:p-2.5 max-[550px]:text-[10px]"
        onClick={onStartDemo}
      >
        <Play size={16} /> Start demo
      </button>
    </div>
  );
}
