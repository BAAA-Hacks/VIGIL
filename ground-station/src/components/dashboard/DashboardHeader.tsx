import { ChevronRight } from "lucide-react";
export function DashboardHeader({ demo }: { demo: boolean }) {
  return (
    <header className="h-[78px] [border-bottom:1px_solid_color-mix(in_srgb,_var(--color-ink)_25%,_transparent)] flex items-center justify-between max-[550px]:h-[65px]">
      <div className=" flex items-center gap-3.5 text-[color:var(--color-ink)]/70 text-[12px] max-[550px]:text-[10px] max-[550px]:gap-1.5">
        Workspace <ChevronRight size={14} /> Ground station
      </div>
      <div className=" flex gap-[18px] items-center">
        <span className=" text-[9px] tracking-[1px] text-[color:var(--color-peach)] border border-[color:var(--color-peach)]/35 bg-[var(--color-peach)]/12 py-1.5 px-[9px] rounded-[4px] max-[550px]:text-[7px]">
          {demo ? "SIMULATION MODE" : "LIVE INPUT MODE"}
        </span>
        <span className=" bg-[var(--color-paper)] border border-[color:var(--color-ink)]/25 rounded-full p-2.5 text-[10px]">
          OP
        </span>
      </div>
    </header>
  );
}
